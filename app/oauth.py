from urllib.parse import urlencode

import httpx

from app.config import settings


def get_authorization_url() -> str:
    """Build the FamilySearch OAuth authorization URL."""
    params = {
        "response_type": "code",
        "client_id": settings.FAMILYSEARCH_CLIENT_ID,
        "redirect_uri": settings.FAMILYSEARCH_REDIRECT_URI,
    }
    return f"{settings.FAMILYSEARCH_AUTH_URL}/authorization?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> dict | None:
    """Exchange authorization code for access + refresh tokens.

    Returns dict with 'access_token', 'refresh_token', or None on failure.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.FAMILYSEARCH_AUTH_URL}/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.FAMILYSEARCH_CLIENT_ID,
                "redirect_uri": settings.FAMILYSEARCH_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15.0,
        )
        if response.status_code != 200:
            return None

        data = response.json()
        return {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
        }


async def refresh_access_token(refresh_token: str) -> dict | None:
    """Use refresh token to get a new access token.

    Returns dict with 'access_token', 'refresh_token', or None on failure.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.FAMILYSEARCH_AUTH_URL}/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.FAMILYSEARCH_CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15.0,
        )
        if response.status_code != 200:
            return None

        data = response.json()
        return {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token", refresh_token),
        }
