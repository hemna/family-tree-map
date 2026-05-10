import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.session import SessionStore
from app.oauth import get_authorization_url, exchange_code_for_token
from app.ancestry import fetch_ancestry, fetch_current_user_parents
from app.geocoding import GeocodingService

app = FastAPI(title="Family Tree Map")

templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

session_store = SessionStore(secret_key=settings.SECRET_KEY)
geocoding_service = GeocodingService()

# Static mode: load people metadata from data/ directory
PEOPLE_DATA: dict[str, dict] = {}  # {person_id: {"name": ..., "files": [...], ...}}
_data_dir = Path("data")
_manifest_file = _data_dir / "manifest.json"

if _manifest_file.exists() and not settings.FAMILYSEARCH_CLIENT_ID:
    manifest = json.loads(_manifest_file.read_text())
    for person in manifest.get("people", []):
        files = person.get("files", [])
        if not files and person.get("file"):
            files = [person["file"]]

        PEOPLE_DATA[person["id"]] = {
            "name": person["name"],
            "files": files,
            "familysearch_id": person.get("familysearch_id", ""),
        }

# Fallback: load ancestors.json if no manifest but file exists
if not PEOPLE_DATA:
    _ancestors_file = Path("ancestors.json")
    if _ancestors_file.exists() and not settings.FAMILYSEARCH_CLIENT_ID:
        PEOPLE_DATA["default"] = {
            "name": "Family Tree",
            "files": [],
            "familysearch_id": "",
            "_static_data": json.loads(_ancestors_file.read_text()),
        }


def _load_person_ancestors(person_id: str) -> list:
    """Load ancestors from disk for a person. Called per-request to get fresh data."""
    person = PEOPLE_DATA.get(person_id)
    if not person:
        return []

    # Fallback for legacy single-file mode
    if "_static_data" in person:
        return person["_static_data"]

    all_ancestors = []
    seen_ids = set()
    for f in person.get("files", []):
        data_file = _data_dir / f
        if data_file.exists():
            try:
                file_data = json.loads(data_file.read_text())
                for ancestor in file_data:
                    if ancestor["id"] not in seen_ids:
                        seen_ids.add(ancestor["id"])
                        all_ancestors.append(ancestor)
            except (json.JSONDecodeError, KeyError):
                pass
    return all_ancestors

STATIC_MODE = bool(PEOPLE_DATA)

SESSION_COOKIE = "session_id"


def _get_session_id(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)


def _get_session(request: Request) -> dict | None:
    session_id = _get_session_id(request)
    if not session_id:
        return None
    return session_store.get(session_id)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if STATIC_MODE:
        # If only one person, go straight to their map
        if len(PEOPLE_DATA) == 1:
            person_id = list(PEOPLE_DATA.keys())[0]
            return RedirectResponse(url=f"/map/{person_id}")
        # Build counts for display
        people_with_counts = {}
        for pid, pdata in PEOPLE_DATA.items():
            ancestors = _load_person_ancestors(pid)
            people_with_counts[pid] = {
                "name": pdata["name"],
                "count": len(ancestors),
            }
        return templates.TemplateResponse(
            request, "select_person.html",
            context={"people": people_with_counts}
        )
    return templates.TemplateResponse(request, "index.html")


@app.get("/map/{person_id}", response_class=HTMLResponse)
async def map_view_person(request: Request, person_id: str):
    """Map view for a specific person's data (static mode)."""
    if not STATIC_MODE:
        return RedirectResponse(url="/")

    # Special case: common ancestors view
    if person_id == "common":
        return await _common_ancestors_view(request)

    if person_id not in PEOPLE_DATA:
        return RedirectResponse(url="/")

    person_meta = PEOPLE_DATA[person_id]
    people_for_template = _people_for_switcher()

    return templates.TemplateResponse(
        request, "map.html",
        context={
            "static_mode": True,
            "person_name": person_meta["name"],
            "people": people_for_template,
            "current_person_id": person_id,
        }
    )


@app.get("/api/ancestors/{person_id}")
async def api_ancestors(person_id: str):
    """Serve ancestor data as JSON endpoint."""
    if person_id == "common":
        # Compute common ancestors
        people_ids = list(PEOPLE_DATA.keys())
        if len(people_ids) < 2:
            return JSONResponse([])

        all_people_ancestors = {}
        for pid in people_ids:
            all_people_ancestors[pid] = _load_person_ancestors(pid)

        common_ids = set(a["id"] for a in all_people_ancestors[people_ids[0]])
        for pid in people_ids[1:]:
            common_ids &= set(a["id"] for a in all_people_ancestors[pid])

        first_ancestors = {a["id"]: a for a in all_people_ancestors[people_ids[0]]}
        second_ancestors = {a["id"]: a for a in all_people_ancestors[people_ids[1]]}

        common_ancestors = []
        for aid in common_ids:
            ancestor = dict(first_ancestors[aid])
            second_rel = second_ancestors[aid]["relationship"] if aid in second_ancestors else ""
            first_name = PEOPLE_DATA[people_ids[0]]["name"].split()[0]
            second_name = PEOPLE_DATA[people_ids[1]]["name"].split()[0]
            ancestor["relationship"] = (
                f"{first_name}: {ancestor['relationship']}<br>"
                f"{second_name}: {second_rel}"
            )
            ancestor["side"] = "common"
            common_ancestors.append(ancestor)

        return JSONResponse(common_ancestors)

    if person_id not in PEOPLE_DATA:
        return JSONResponse([])

    ancestors = _load_person_ancestors(person_id)
    return JSONResponse(ancestors)


@app.get("/api/lineage/{ancestor_id}")
async def api_lineage(ancestor_id: str):
    """Return lineage paths to a specific ancestor from all people's trees."""
    people_ids = list(PEOPLE_DATA.keys())
    result = {}

    for pid in people_ids:
        ancestors = _load_person_ancestors(pid)
        ancestor_map = {a["id"]: a for a in ancestors}

        if ancestor_id not in ancestor_map:
            continue

        # Trace path from ancestor back to generation 1 via child_id
        path = []
        current = ancestor_map[ancestor_id]
        while current:
            path.append({
                "id": current["id"],
                "name": current["name"],
                "relationship": current["relationship"],
                "generation": current["generation"],
                "familysearch_url": current.get("familysearch_url", ""),
            })
            child_id = current.get("child_id")
            if child_id and child_id in ancestor_map:
                current = ancestor_map[child_id]
            else:
                break

        path.reverse()  # From closest to furthest
        result[pid] = {
            "name": PEOPLE_DATA[pid]["name"],
            "path": path,
        }

    return JSONResponse(result)


def _people_for_switcher() -> dict:
    """Build people dict for the template switcher dropdown, including common view."""
    result = {pid: {"name": p["name"]} for pid, p in PEOPLE_DATA.items()}
    # Add common ancestors option if there are 2+ people
    if len(PEOPLE_DATA) >= 2:
        result["common"] = {"name": "Common Ancestors"}
    return result


async def _common_ancestors_view(request: Request):
    """Show ancestors shared between all people in the dataset."""
    people_for_template = _people_for_switcher()

    return templates.TemplateResponse(
        request, "map.html",
        context={
            "static_mode": True,
            "person_name": "Common Ancestors",
            "people": people_for_template,
            "current_person_id": "common",
        }
    )


@app.get("/map", response_class=HTMLResponse)
async def map_view(request: Request):
    if STATIC_MODE:
        person_id = list(PEOPLE_DATA.keys())[0]
        return RedirectResponse(url=f"/map/{person_id}")

    session = _get_session(request)
    if not session:
        return RedirectResponse(url="/")

    ancestors = session.get("ancestors", [])
    return templates.TemplateResponse(
        request, "map.html",
        context={
            "static_mode": False,
            "person_name": "",
            "people": {},
            "current_person_id": "",
        }
    )


@app.get("/login")
async def login():
    url = get_authorization_url()
    return RedirectResponse(url=url)


@app.get("/callback")
async def callback(request: Request, code: str = ""):
    if not code:
        return RedirectResponse(url="/?error=auth_failed")

    tokens = await exchange_code_for_token(code)
    if not tokens:
        return RedirectResponse(url="/?error=auth_failed")

    session_id = session_store.create()
    session_store.update(session_id, {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
    })

    response = RedirectResponse(url="/select-lineage", status_code=303)
    response.set_cookie(
        SESSION_COOKIE, session_id, httponly=True, samesite="lax"
    )
    return response


@app.get("/select-lineage", response_class=HTMLResponse)
async def select_lineage(request: Request):
    session = _get_session(request)
    if not session:
        return RedirectResponse(url="/")

    access_token = session.get("access_token", "")
    parent_info = await fetch_current_user_parents(access_token)

    parents = parent_info["parents"]

    if len(parents) == 1:
        parent = parents[0]
        side = "paternal" if parent["gender"] == "Male" else "maternal"
        session_id = _get_session_id(request)
        session_store.set(session_id, "fetch_status", "running")
        asyncio.create_task(
            fetch_ancestry(
                parent["id"], side, access_token, geocoding_service, session
            )
        )
        return templates.TemplateResponse(request, "loading.html")

    if len(parents) == 0:
        return templates.TemplateResponse(
            request,
            "select_lineage.html",
            context={
                "user_name": parent_info["user_name"],
                "parents": [],
                "error": "No parent records found in FamilySearch.",
            },
        )

    return templates.TemplateResponse(
        request,
        "select_lineage.html",
        context={
            "user_name": parent_info["user_name"],
            "parents": parents,
            "error": None,
        },
    )


@app.post("/fetch-ancestry", response_class=HTMLResponse)
async def start_fetch_ancestry(request: Request, side: str = Form(...), parent_id: str = Form(...)):
    session = _get_session(request)
    if not session:
        return RedirectResponse(url="/")

    session_id = _get_session_id(request)
    access_token = session.get("access_token", "")

    asyncio.create_task(
        fetch_ancestry(parent_id, side, access_token, geocoding_service, session)
    )

    return templates.TemplateResponse(request, "loading.html")


@app.get("/api/ancestry-status")
async def ancestry_status(request: Request):
    session = _get_session(request)
    if not session:
        return JSONResponse({"status": "error", "error_detail": "Not authenticated"})

    status = session.get("fetch_status", "idle")
    count = session.get("fetch_count", 0)
    geocoded = session.get("geocoded_count", 0)
    error = session.get("fetch_error")

    if status == "running":
        message = f"Found {count} ancestors, geocoded {geocoded} locations..."
    elif status == "done" and error:
        message = error
    elif status == "done":
        message = f"Complete! Found {count} ancestors with {geocoded} map locations."
    else:
        message = error or "Unknown status"

    return JSONResponse({
        "status": status,
        "count": count,
        "geocoded_count": geocoded,
        "message": message,
        "error_detail": error if status == "error" else None,
    })


@app.get("/logout")
async def logout(request: Request):
    session_id = _get_session_id(request)
    if session_id:
        session_store.delete(session_id)
    response = RedirectResponse(url="/")
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/api/scrape-status")
async def scrape_status():
    """Return scraping progress by reading log files."""
    import subprocess

    log_dir = Path(".")
    status = {}

    # Map log files to person/side
    log_mapping = {
        "scrape_walter_paternal.log": {"person": "walter", "side": "paternal"},
        "scrape_walter_maternal.log": {"person": "walter", "side": "maternal"},
        "scrape_wife_paternal.log": {"person": "wife", "side": "paternal"},
        "scrape_wife_maternal.log": {"person": "wife", "side": "maternal"},
    }

    for log_file, info in log_mapping.items():
        log_path = log_dir / log_file
        key = f"{info['person']}_{info['side']}"

        if not log_path.exists():
            status[key] = {"status": "not_started", "count": 0, "last_line": ""}
            continue

        # Read last few lines to get progress
        try:
            content = log_path.read_text()
            lines = content.strip().split("\n")
            last_line = lines[-1] if lines else ""

            # Check if done
            if "Done!" in content:
                # Extract final count
                for line in reversed(lines):
                    if "Done!" in line:
                        status[key] = {"status": "done", "count": 0, "last_line": line}
                        # Try to parse count
                        if "Found " in line:
                            try:
                                count = int(line.split("Found ")[1].split(" ")[0])
                                status[key]["count"] = count
                            except (IndexError, ValueError):
                                pass
                        break
            else:
                # Parse progress from last line like "[1234/99999] Gen 8: ..."
                count = 0
                if "[" in last_line and "/" in last_line:
                    try:
                        count = int(last_line.split("[")[1].split("/")[0])
                    except (IndexError, ValueError):
                        pass

                # Check if process is still running
                result = subprocess.run(
                    ["pgrep", "-f", f"-o {info['person']}_{info['side']}.json"],
                    capture_output=True, text=True
                )
                # Also check by output file name
                result2 = subprocess.run(
                    ["pgrep", "-f", f"data/{info['person']}_{info['side']}.json"],
                    capture_output=True, text=True
                )
                is_running = bool(result.stdout.strip() or result2.stdout.strip())

                status[key] = {
                    "status": "running" if is_running else "stopped",
                    "count": count,
                    "last_line": last_line[-100:] if last_line else "",
                }
        except Exception as e:
            status[key] = {"status": "error", "count": 0, "last_line": str(e)}

    return JSONResponse(status)
