import asyncio
import sqlite3
import time
from datetime import datetime, timezone

import httpx

from app.config import settings


class GeoCache:
    def __init__(self, db_path: str = "geocache.db"):
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS geocache (
                place_string TEXT PRIMARY KEY,
                lat REAL NOT NULL,
                lng REAL NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def get(self, place_string: str) -> tuple[float, float] | None:
        cursor = self._conn.execute(
            "SELECT lat, lng FROM geocache WHERE place_string = ?",
            (place_string,),
        )
        row = cursor.fetchone()
        return (row[0], row[1]) if row else None

    def put(self, place_string: str, lat: float, lng: float, source: str) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO geocache (place_string, lat, lng, source, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (place_string, lat, lng, source, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


class GeocodingService:
    def __init__(self, cache_path: str = "geocache.db"):
        self.cache = GeoCache(cache_path)
        self._last_nominatim_call: float = 0.0
        self._nominatim_lock = asyncio.Lock()

    async def geocode(
        self, place_string: str, access_token: str
    ) -> tuple[float, float] | None:
        if not place_string:
            return None

        cached = self.cache.get(place_string)
        if cached:
            return cached

        result = await self._query_familysearch_places(place_string, access_token)
        if result:
            self.cache.put(place_string, result[0], result[1], "familysearch")
            return result

        result = await self._query_nominatim(place_string)
        if result:
            self.cache.put(place_string, result[0], result[1], "nominatim")
            return result

        return None

    async def _query_familysearch_places(
        self, place_string: str, access_token: str
    ) -> tuple[float, float] | None:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.FAMILYSEARCH_BASE_URL}/platform/places/search",
                    params={"q": f'name:"{place_string}"'},
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                    timeout=10.0,
                )
                if response.status_code != 200:
                    return None

                data = response.json()
                entries = data.get("entries", [])
                if not entries:
                    return None

                content = entries[0].get("content", {})
                place = content.get("gedcomx", {}).get("places", [{}])[0]
                lat = place.get("latitude")
                lng = place.get("longitude")
                if lat is not None and lng is not None:
                    return (float(lat), float(lng))
        except Exception:
            pass
        return None

    async def _query_nominatim(
        self, place_string: str
    ) -> tuple[float, float] | None:
        async with self._nominatim_lock:
            elapsed = time.time() - self._last_nominatim_call
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)

            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{settings.NOMINATIM_BASE_URL}/search",
                        params={"q": place_string, "format": "json", "limit": "1"},
                        headers={"User-Agent": "FamilyTreeMap/0.1"},
                        timeout=10.0,
                    )
                    self._last_nominatim_call = time.time()

                    if response.status_code != 200:
                        return None

                    results = response.json()
                    if not results:
                        return None

                    return (float(results[0]["lat"]), float(results[0]["lon"]))
            except Exception:
                self._last_nominatim_call = time.time()
                return None

    def close(self) -> None:
        self.cache.close()
