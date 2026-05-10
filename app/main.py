import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Form, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.session import SessionStore
from app.oauth import get_authorization_url, exchange_code_for_token
from app.ancestry import fetch_ancestry, fetch_current_user_parents
from app.geocoding import GeocodingService
from app.database import (
    init_db, get_connection, get_ancestors, get_ancestor_count,
    get_common_ancestors, get_lineage_path, search_ancestors, get_year_range,
    DB_PATH,
)

app = FastAPI(title="Family Tree Map")

templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

session_store = SessionStore(secret_key=settings.SECRET_KEY)
geocoding_service = GeocodingService()

# Initialize database
init_db()

# Check if we're in static/DB mode (no API keys configured, DB exists)
STATIC_MODE = DB_PATH.exists() and not settings.FAMILYSEARCH_CLIENT_ID

# Load people list from database
PEOPLE: dict[str, str] = {}  # {person_id: name}
if STATIC_MODE:
    conn = get_connection()
    cursor = conn.execute("SELECT id, name FROM people")
    for row in cursor.fetchall():
        PEOPLE[row["id"]] = row["name"]
    conn.close()

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
        if len(PEOPLE) == 1:
            person_id = list(PEOPLE.keys())[0]
            return RedirectResponse(url=f"/map/{person_id}")
        # Build counts
        conn = get_connection()
        people_with_counts = {}
        for pid, name in PEOPLE.items():
            count = get_ancestor_count(conn, pid)
            people_with_counts[pid] = {"name": name, "count": count}
        conn.close()
        return templates.TemplateResponse(
            request, "select_person.html",
            context={"people": people_with_counts}
        )
    return templates.TemplateResponse(request, "index.html")


@app.get("/map/{person_id}", response_class=HTMLResponse)
async def map_view_person(request: Request, person_id: str):
    if not STATIC_MODE:
        return RedirectResponse(url="/")

    if person_id == "common":
        person_name = "Common Ancestors"
    elif person_id not in PEOPLE:
        return RedirectResponse(url="/")
    else:
        person_name = PEOPLE[person_id]

    # Build people dict for switcher
    people_for_template = {pid: {"name": name} for pid, name in PEOPLE.items()}
    if len(PEOPLE) >= 2:
        people_for_template["common"] = {"name": "Common Ancestors"}

    return templates.TemplateResponse(
        request, "map.html",
        context={
            "static_mode": True,
            "person_name": person_name,
            "people": people_for_template,
            "current_person_id": person_id,
        }
    )


@app.get("/map", response_class=HTMLResponse)
async def map_view(request: Request):
    if STATIC_MODE:
        person_id = list(PEOPLE.keys())[0]
        return RedirectResponse(url=f"/map/{person_id}")

    session = _get_session(request)
    if not session:
        return RedirectResponse(url="/")

    return templates.TemplateResponse(
        request, "map.html",
        context={
            "static_mode": False,
            "person_name": "",
            "people": {},
            "current_person_id": "",
        }
    )


# --- API Endpoints ---


@app.get("/api/ancestors/{person_id}")
async def api_ancestors(
    request: Request,
    person_id: str,
    side: str | None = Query(None),
    year_min: int | None = Query(None),
    year_max: int | None = Query(None),
    search: str | None = Query(None),
    limit: int | None = Query(None),
    offset: int = Query(0),
):
    """Serve ancestor data with optional server-side filtering."""
    conn = get_connection()

    if person_id == "common":
        people_ids = list(PEOPLE.keys())
        ancestors = get_common_ancestors(conn, people_ids)
        conn.close()
        return JSONResponse(ancestors)

    if person_id not in PEOPLE:
        conn.close()
        return JSONResponse([])

    ancestors = get_ancestors(
        conn, person_id,
        side=side,
        year_min=year_min,
        year_max=year_max,
        search=search,
        limit=limit,
        offset=offset,
    )
    conn.close()
    return JSONResponse(ancestors)


@app.get("/api/ancestors/{person_id}/meta")
async def api_ancestors_meta(person_id: str):
    """Return metadata about a person's ancestors (count, year range)."""
    conn = get_connection()

    if person_id == "common":
        people_ids = list(PEOPLE.keys())
        # Count common ancestors
        placeholders = ",".join(["?"] * len(people_ids))
        cursor = conn.execute(
            f"""SELECT COUNT(DISTINCT id) FROM (
                SELECT id FROM ancestors
                WHERE person_id IN ({placeholders})
                GROUP BY id
                HAVING COUNT(DISTINCT person_id) = ?
            )""",
            (*people_ids, len(people_ids)),
        )
        count = cursor.fetchone()[0]
        conn.close()
        return JSONResponse({"count": count, "year_min": None, "year_max": None})

    if person_id not in PEOPLE:
        conn.close()
        return JSONResponse({"count": 0, "year_min": None, "year_max": None})

    count = get_ancestor_count(conn, person_id)
    year_min, year_max = get_year_range(conn, person_id)
    conn.close()
    return JSONResponse({"count": count, "year_min": year_min, "year_max": year_max})


@app.get("/api/search/{person_id}")
async def api_search(person_id: str, q: str = Query(""), limit: int = Query(15)):
    """Search ancestors by name."""
    if not q or len(q) < 2:
        return JSONResponse([])

    conn = get_connection()
    if person_id == "common":
        # Search across all people, return only common ones
        # For simplicity, search in first person's data
        people_ids = list(PEOPLE.keys())
        if people_ids:
            results = search_ancestors(conn, people_ids[0], q, limit)
        else:
            results = []
    elif person_id in PEOPLE:
        results = search_ancestors(conn, person_id, q, limit)
    else:
        results = []

    conn.close()
    return JSONResponse(results)


@app.get("/api/lineage/{ancestor_id}")
async def api_lineage(ancestor_id: str):
    """Return lineage paths from all people to a specific ancestor."""
    conn = get_connection()
    result = {}

    for pid, name in PEOPLE.items():
        path = get_lineage_path(conn, pid, ancestor_id)
        if path:
            result[pid] = {"name": name, "path": path}

    conn.close()
    return JSONResponse(result)


@app.get("/api/scrape-status")
async def scrape_status():
    """Return scraping progress by reading log files."""
    import subprocess

    log_dir = Path(".")
    status = {}

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

        try:
            content = log_path.read_text()
            lines = content.strip().split("\n")
            last_line = lines[-1] if lines else ""

            if "Done!" in content:
                for line in reversed(lines):
                    if "Done!" in line:
                        status[key] = {"status": "done", "count": 0, "last_line": line}
                        if "Found " in line:
                            try:
                                count = int(line.split("Found ")[1].split(" ")[0])
                                status[key]["count"] = count
                            except (IndexError, ValueError):
                                pass
                        break
            else:
                count = 0
                if "[" in last_line and "/" in last_line:
                    try:
                        count = int(last_line.split("[")[1].split("/")[0])
                    except (IndexError, ValueError):
                        pass

                result2 = subprocess.run(
                    ["pgrep", "-f", f"data/{info['person']}_{info['side']}.json"],
                    capture_output=True, text=True
                )
                is_running = bool(result2.stdout.strip())

                status[key] = {
                    "status": "running" if is_running else "stopped",
                    "count": count,
                    "last_line": last_line[-100:] if last_line else "",
                }
        except Exception as e:
            status[key] = {"status": "error", "count": 0, "last_line": str(e)}

    return JSONResponse(status)


# --- OAuth Routes (for live mode) ---


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
            request, "select_lineage.html",
            context={
                "user_name": parent_info["user_name"],
                "parents": [],
                "error": "No parent records found in FamilySearch.",
            },
        )

    return templates.TemplateResponse(
        request, "select_lineage.html",
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
