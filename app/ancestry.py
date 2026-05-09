import asyncio
import logging

import httpx

from app.config import settings
from app.date_parser import extract_year
from app.geocoding import GeocodingService

logger = logging.getLogger(__name__)


def compute_relationship_label(generation: int, gender: str, side: str) -> str:
    """Compute a relationship label given generation depth, gender, and side."""
    if gender == "Male":
        base = "father"
    else:
        base = "mother"

    if generation == 1:
        title = base
    elif generation == 2:
        title = f"grand{base}"
    elif generation == 3:
        title = f"great-grand{base}"
    else:
        n = generation - 2
        suffix = _ordinal_suffix(n)
        title = f"{n}{suffix} great-grand{base}"

    return f"{side} {title}"


def _ordinal_suffix(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


async def fetch_ancestry(
    parent_id: str,
    side: str,
    access_token: str,
    geocoding_service: GeocodingService,
    session_data: dict,
) -> None:
    """Recursively fetch ancestors starting from parent_id.
    Updates session_data in place with progress and results.
    """
    session_data["fetch_status"] = "running"
    session_data["fetch_count"] = 0
    session_data["geocoded_count"] = 0
    session_data["ancestors"] = []
    session_data["fetch_error"] = None

    try:
        ancestors = []
        queue: list[tuple[str, int]] = [(parent_id, 1)]
        visited: set[str] = set()

        async with httpx.AsyncClient() as client:
            while queue and len(ancestors) < settings.MAX_ANCESTORS:
                person_id, generation = queue.pop(0)

                if person_id in visited:
                    continue
                visited.add(person_id)

                person_data = await _fetch_person(client, person_id, access_token)
                if person_data is None:
                    continue

                name = _extract_name(person_data)
                gender = _extract_gender(person_data)
                birth_info = _extract_event(person_data, "http://gedcomx.org/Birth")
                death_info = _extract_event(person_data, "http://gedcomx.org/Death")

                birth_coords = None
                death_coords = None

                if birth_info.get("place"):
                    birth_coords = await geocoding_service.geocode(
                        birth_info["place"], access_token
                    )
                    if birth_coords:
                        session_data["geocoded_count"] += 1

                if death_info.get("place"):
                    death_coords = await geocoding_service.geocode(
                        death_info["place"], access_token
                    )
                    if death_coords:
                        session_data["geocoded_count"] += 1

                ancestor = {
                    "id": person_id,
                    "name": name,
                    "gender": gender,
                    "relationship": compute_relationship_label(generation, gender, side),
                    "generation": generation,
                    "side": side,
                    "birth": {
                        "date_original": birth_info.get("date"),
                        "date_year": extract_year(birth_info.get("date")),
                        "place": birth_info.get("place"),
                        "lat": birth_coords[0] if birth_coords else None,
                        "lng": birth_coords[1] if birth_coords else None,
                    },
                    "death": {
                        "date_original": death_info.get("date"),
                        "date_year": extract_year(death_info.get("date")),
                        "place": death_info.get("place"),
                        "lat": death_coords[0] if death_coords else None,
                        "lng": death_coords[1] if death_coords else None,
                    },
                    "familysearch_url": f"https://www.familysearch.org/tree/person/details/{person_id}",
                }

                ancestors.append(ancestor)
                session_data["fetch_count"] = len(ancestors)
                session_data["ancestors"] = ancestors

                parents = await _fetch_parents(client, person_id, access_token)
                for pid in parents:
                    if pid not in visited:
                        queue.append((pid, generation + 1))

        if len(ancestors) >= settings.MAX_ANCESTORS:
            session_data["fetch_status"] = "done"
            session_data["fetch_error"] = (
                f"Reached maximum of {settings.MAX_ANCESTORS} ancestors. "
                "Deeper ancestors not included."
            )
        else:
            session_data["fetch_status"] = "done"

    except Exception as e:
        logger.exception("Ancestry fetch failed")
        session_data["fetch_status"] = "error"
        session_data["fetch_error"] = str(e)


async def fetch_current_user_parents(access_token: str) -> dict:
    """Fetch the current user's person and their parents."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.FAMILYSEARCH_BASE_URL}/platform/tree/current-person",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=15.0,
        )
        if response.status_code != 200:
            return {"user_name": "Unknown", "parents": []}

        data = response.json()
        persons = data.get("persons", [])
        if not persons:
            return {"user_name": "Unknown", "parents": []}

        user_person = persons[0]
        user_id = user_person.get("id", "")
        user_name = _extract_name(user_person)

        response = await client.get(
            f"{settings.FAMILYSEARCH_BASE_URL}/platform/tree/persons/{user_id}/parents",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=15.0,
        )
        if response.status_code != 200:
            return {"user_name": user_name, "parents": []}

        data = response.json()
        parents = []
        for person in data.get("persons", []):
            parents.append({
                "id": person.get("id", ""),
                "name": _extract_name(person),
                "gender": _extract_gender(person),
            })

        return {"user_name": user_name, "parents": parents}


async def _fetch_person(
    client: httpx.AsyncClient, person_id: str, access_token: str
) -> dict | None:
    try:
        response = await client.get(
            f"{settings.FAMILYSEARCH_BASE_URL}/platform/tree/persons/{person_id}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=15.0,
        )
        if response.status_code != 200:
            return None
        data = response.json()
        persons = data.get("persons", [])
        return persons[0] if persons else None
    except Exception:
        return None


async def _fetch_parents(
    client: httpx.AsyncClient, person_id: str, access_token: str
) -> list[str]:
    try:
        response = await client.get(
            f"{settings.FAMILYSEARCH_BASE_URL}/platform/tree/persons/{person_id}/parents",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=15.0,
        )
        if response.status_code != 200:
            return []
        data = response.json()
        parent_ids = []
        for person in data.get("persons", []):
            pid = person.get("id")
            if pid:
                parent_ids.append(pid)
        return parent_ids
    except Exception:
        return []


def _extract_name(person: dict) -> str:
    display = person.get("display", {})
    name = display.get("name")
    if name:
        return name
    names = person.get("names", [])
    if names:
        name_forms = names[0].get("nameForms", [])
        if name_forms:
            return name_forms[0].get("fullText", "Unknown")
    return "Unknown"


def _extract_gender(person: dict) -> str:
    display = person.get("display", {})
    gender = display.get("gender")
    if gender:
        return gender
    gender_obj = person.get("gender", {})
    gtype = gender_obj.get("type", "")
    if "Male" in gtype:
        return "Male"
    elif "Female" in gtype:
        return "Female"
    return "Unknown"


def _extract_event(person: dict, event_type: str) -> dict:
    facts = person.get("facts", [])
    for fact in facts:
        if fact.get("type") == event_type:
            date_str = None
            place_str = None
            date_obj = fact.get("date", {})
            if date_obj:
                date_str = date_obj.get("original")
            place_obj = fact.get("place", {})
            if place_obj:
                place_str = place_obj.get("original")
            return {"date": date_str, "place": place_str}
    return {"date": None, "place": None}
