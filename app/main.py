import asyncio

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
    return templates.TemplateResponse(request, "index.html")


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


@app.get("/map", response_class=HTMLResponse)
async def map_view(request: Request):
    session = _get_session(request)
    if not session:
        return RedirectResponse(url="/")

    ancestors = session.get("ancestors", [])
    return templates.TemplateResponse(
        request, "map.html", context={"ancestors": ancestors}
    )


@app.get("/logout")
async def logout(request: Request):
    session_id = _get_session_id(request)
    if session_id:
        session_store.delete(session_id)
    response = RedirectResponse(url="/")
    response.delete_cookie(SESSION_COOKIE)
    return response
