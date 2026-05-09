#!/usr/bin/env python3
"""
Scrape ancestry data from FamilySearch and save to JSON.

This script:
1. Starts a tiny local HTTP server
2. Opens your browser to FamilySearch OAuth login
3. Captures the auth token after you log in
4. Fetches your ancestry recursively
5. Geocodes places
6. Saves everything to ancestors.json

Usage:
    python scrape_ancestry.py --client-id YOUR_CLIENT_ID [--side paternal|maternal] [--max 500]

If you don't have a client ID yet, you can use --token YOUR_TOKEN to skip OAuth
and provide a token you grabbed from a browser session manually.

To get a token manually:
    1. Log into familysearch.org
    2. Open browser dev tools > Application > Cookies
    3. Copy the 'fssessionid' cookie value
    4. Run: python scrape_ancestry.py --token YOUR_FSSESSIONID
"""
import argparse
import asyncio
import http.server
import json
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

# FamilySearch API base URLs
FS_API_BASE = "https://api.familysearch.org"
FS_AUTH_URL = "https://ident.familysearch.org/cis-web/oauth2/v3"
NOMINATIM_URL = "https://nominatim.openstreetmap.org"

# Rate limiting for Nominatim
last_nominatim_call = 0.0


def extract_year(date_string: str | None) -> int | None:
    """Extract a 4-digit year from a FamilySearch date string."""
    import re
    if not date_string:
        return None
    matches = re.findall(r"\b(\d{4})\b", date_string)
    for match in matches:
        year = int(match)
        if 1000 <= year <= 2100:
            return year
    return None


def compute_relationship_label(generation: int, gender: str, side: str) -> str:
    """Compute relationship label."""
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
        if 11 <= n % 100 <= 13:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        title = f"{n}{suffix} great-grand{base}"

    return f"{side} {title}"


async def get_token_via_oauth(client_id: str) -> str:
    """Open browser for OAuth login and capture the token."""
    redirect_uri = "http://localhost:8765/callback"
    auth_code_holder = {"code": None}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if "code" in params:
                auth_code_holder["code"] = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Success!</h1><p>You can close this window.</p>")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"<h1>Error</h1><p>No auth code received.</p>")

        def log_message(self, format, *args):
            pass  # Suppress server logs

    server = http.server.HTTPServer(("localhost", 8765), CallbackHandler)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    auth_params = urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    })
    auth_url = f"{FS_AUTH_URL}/authorization?{auth_params}"

    print(f"\nOpening browser for FamilySearch login...")
    print(f"If browser doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for callback
    server_thread.join(timeout=120)
    server.server_close()

    if not auth_code_holder["code"]:
        print("ERROR: No authorization code received. Timed out.")
        sys.exit(1)

    # Exchange code for token
    print("Got authorization code, exchanging for token...")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{FS_AUTH_URL}/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code_holder["code"],
                "client_id": client_id,
                "redirect_uri": redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15.0,
        )
        if response.status_code != 200:
            print(f"ERROR: Token exchange failed: {response.status_code}")
            print(response.text)
            sys.exit(1)
        data = response.json()
        return data["access_token"]


async def geocode_place(place: str, access_token: str, cache: dict) -> tuple[float, float] | None:
    """Geocode a place string. Uses cache to avoid repeated lookups."""
    global last_nominatim_call

    if not place:
        return None

    if place in cache:
        return cache[place]

    # Try FamilySearch Places API
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{FS_API_BASE}/platform/places/search",
                params={"q": f'name:"{place}"'},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                timeout=10.0,
            )
            if response.status_code == 200:
                data = response.json()
                entries = data.get("entries", [])
                if entries:
                    content = entries[0].get("content", {})
                    places = content.get("gedcomx", {}).get("places", [])
                    if places:
                        lat = places[0].get("latitude")
                        lng = places[0].get("longitude")
                        if lat is not None and lng is not None:
                            result = (float(lat), float(lng))
                            cache[place] = result
                            return result
    except Exception:
        pass

    # Fallback to Nominatim (rate limited)
    elapsed = time.time() - last_nominatim_call
    if elapsed < 1.0:
        await asyncio.sleep(1.0 - elapsed)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{NOMINATIM_URL}/search",
                params={"q": place, "format": "json", "limit": "1"},
                headers={"User-Agent": "FamilyTreeMapScraper/0.1"},
                timeout=10.0,
            )
            last_nominatim_call = time.time()
            if response.status_code == 200:
                results = response.json()
                if results:
                    result = (float(results[0]["lat"]), float(results[0]["lon"]))
                    cache[place] = result
                    return result
    except Exception:
        last_nominatim_call = time.time()

    cache[place] = None
    return None


async def fetch_person(client: httpx.AsyncClient, person_id: str, token: str) -> dict | None:
    """Fetch a single person's details."""
    try:
        response = await client.get(
            f"{FS_API_BASE}/platform/tree/persons/{person_id}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15.0,
        )
        if response.status_code != 200:
            return None
        data = response.json()
        persons = data.get("persons", [])
        return persons[0] if persons else None
    except Exception as e:
        print(f"  Warning: Failed to fetch {person_id}: {e}")
        return None


async def fetch_parents(client: httpx.AsyncClient, person_id: str, token: str) -> list[str]:
    """Fetch parent IDs for a person."""
    try:
        response = await client.get(
            f"{FS_API_BASE}/platform/tree/persons/{person_id}/parents",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15.0,
        )
        if response.status_code != 200:
            return []
        data = response.json()
        return [p["id"] for p in data.get("persons", []) if p.get("id")]
    except Exception:
        return []


def extract_name(person: dict) -> str:
    display = person.get("display", {})
    name = display.get("name")
    if name:
        return name
    names = person.get("names", [])
    if names:
        forms = names[0].get("nameForms", [])
        if forms:
            return forms[0].get("fullText", "Unknown")
    return "Unknown"


def extract_gender(person: dict) -> str:
    display = person.get("display", {})
    gender = display.get("gender")
    if gender:
        return gender
    g = person.get("gender", {}).get("type", "")
    if "Male" in g:
        return "Male"
    elif "Female" in g:
        return "Female"
    return "Unknown"


def extract_event(person: dict, event_type: str) -> dict:
    for fact in person.get("facts", []):
        if fact.get("type") == event_type:
            date_obj = fact.get("date", {})
            place_obj = fact.get("place", {})
            return {
                "date": date_obj.get("original") if date_obj else None,
                "place": place_obj.get("original") if place_obj else None,
            }
    return {"date": None, "place": None}


async def scrape(token: str, side: str | None, max_ancestors: int, output_file: str):
    """Main scraping function."""
    geocache: dict = {}
    ancestors = []

    async with httpx.AsyncClient() as client:
        # Get current user's person
        print("Fetching your person record...")
        response = await client.get(
            f"{FS_API_BASE}/platform/tree/current-person",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15.0,
        )
        if response.status_code != 200:
            print(f"ERROR: Could not fetch current person (status {response.status_code})")
            print("Your token may be invalid or expired.")
            sys.exit(1)

        data = response.json()
        persons = data.get("persons", [])
        if not persons:
            print("ERROR: No person data returned")
            sys.exit(1)

        user_person = persons[0]
        user_id = user_person.get("id")
        user_name = extract_name(user_person)
        print(f"Logged in as: {user_name} ({user_id})")

        # Get parents
        print("Fetching parents...")
        response = await client.get(
            f"{FS_API_BASE}/platform/tree/persons/{user_id}/parents",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15.0,
        )
        if response.status_code != 200:
            print("ERROR: Could not fetch parents")
            sys.exit(1)

        parent_data = response.json()
        parents = []
        for p in parent_data.get("persons", []):
            parents.append({
                "id": p.get("id"),
                "name": extract_name(p),
                "gender": extract_gender(p),
            })

        if not parents:
            print("No parents found in your tree.")
            sys.exit(1)

        # Select side
        if side is None:
            print("\nYour parents:")
            for i, p in enumerate(parents):
                label = "Father" if p["gender"] == "Male" else "Mother"
                print(f"  {i+1}. {p['name']} ({label})")

            if len(parents) == 1:
                choice = 0
            else:
                choice_str = input("\nSelect parent (1 or 2): ").strip()
                choice = int(choice_str) - 1

            selected_parent = parents[choice]
            side = "paternal" if selected_parent["gender"] == "Male" else "maternal"
        else:
            # Find parent matching requested side
            selected_parent = None
            for p in parents:
                if side == "paternal" and p["gender"] == "Male":
                    selected_parent = p
                    break
                elif side == "maternal" and p["gender"] == "Female":
                    selected_parent = p
                    break
            if not selected_parent:
                print(f"ERROR: No {side} parent found")
                sys.exit(1)

        print(f"\nFetching {side} ancestry starting from {selected_parent['name']}...")
        print(f"Max ancestors: {max_ancestors}")
        print()

        # BFS fetch ancestry
        queue = [(selected_parent["id"], 1)]
        visited = set()

        while queue and len(ancestors) < max_ancestors:
            person_id, generation = queue.pop(0)

            if person_id in visited:
                continue
            visited.add(person_id)

            person_data = await fetch_person(client, person_id, token)
            if person_data is None:
                continue

            name = extract_name(person_data)
            gender = extract_gender(person_data)
            birth_info = extract_event(person_data, "http://gedcomx.org/Birth")
            death_info = extract_event(person_data, "http://gedcomx.org/Death")

            # Geocode
            birth_coords = await geocode_place(birth_info.get("place"), token, geocache)
            death_coords = await geocode_place(death_info.get("place"), token, geocache)

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

            geocoded = sum(1 for a in ancestors
                          if (a["birth"]["lat"] is not None) or (a["death"]["lat"] is not None))
            print(f"  [{len(ancestors)}/{max_ancestors}] Gen {generation}: {name} "
                  f"({ancestor['relationship']}) — {geocoded} geocoded")

            # Queue parents
            parent_ids = await fetch_parents(client, person_id, token)
            for pid in parent_ids:
                if pid not in visited:
                    queue.append((pid, generation + 1))

    # Save to file
    output_path = Path(output_file)
    output_path.write_text(json.dumps(ancestors, indent=2, ensure_ascii=False))

    geocoded_count = sum(1 for a in ancestors
                        if a["birth"]["lat"] is not None or a["death"]["lat"] is not None)
    print(f"\nDone! Found {len(ancestors)} ancestors, {geocoded_count} with map locations.")
    print(f"Saved to: {output_path.resolve()}")

    # Also save geocache for reuse
    cache_path = output_path.parent / "geocache.json"
    serializable_cache = {k: v for k, v in geocache.items() if v is not None}
    cache_path.write_text(json.dumps(serializable_cache, indent=2, ensure_ascii=False))
    print(f"Geocache saved to: {cache_path.resolve()} ({len(serializable_cache)} entries)")


def main():
    parser = argparse.ArgumentParser(description="Scrape FamilySearch ancestry to JSON")
    parser.add_argument("--client-id", help="FamilySearch OAuth client ID")
    parser.add_argument("--token", help="Pre-existing access token (skip OAuth)")
    parser.add_argument("--side", choices=["paternal", "maternal"],
                        help="Which side to fetch (prompts if not specified)")
    parser.add_argument("--max", type=int, default=500,
                        help="Maximum ancestors to fetch (default: 500)")
    parser.add_argument("--output", "-o", default="ancestors.json",
                        help="Output JSON file (default: ancestors.json)")

    args = parser.parse_args()

    if not args.token and not args.client_id:
        print("ERROR: Provide either --client-id (for OAuth login) or --token (manual)")
        print()
        print("To get a token manually:")
        print("  1. Log into familysearch.org in your browser")
        print("  2. Open dev tools > Application > Cookies")
        print("  3. Copy the 'fssessionid' cookie value")
        print("  4. Run: python scrape_ancestry.py --token YOUR_TOKEN")
        sys.exit(1)

    if args.token:
        token = args.token
    else:
        token = asyncio.run(get_token_via_oauth(args.client_id))

    asyncio.run(scrape(token, args.side, args.max, args.output))


if __name__ == "__main__":
    main()
