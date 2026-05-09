import sqlite3
import tempfile
import os
from unittest.mock import AsyncMock, patch

import pytest

from app.geocoding import GeocodingService, GeoCache


class TestGeoCache:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.cache = GeoCache(self.tmp.name)

    def teardown_method(self):
        self.cache.close()
        os.unlink(self.tmp.name)

    def test_get_miss(self):
        result = self.cache.get("Nonexistent Place")
        assert result is None

    def test_put_and_get(self):
        self.cache.put("Hamburg, Germany", 53.55, 9.99, "nominatim")
        result = self.cache.get("Hamburg, Germany")
        assert result == (53.55, 9.99)

    def test_put_overwrites(self):
        self.cache.put("Hamburg, Germany", 53.55, 9.99, "nominatim")
        self.cache.put("Hamburg, Germany", 53.56, 9.98, "familysearch")
        result = self.cache.get("Hamburg, Germany")
        assert result == (53.56, 9.98)


class TestGeocodingService:
    @pytest.mark.asyncio
    async def test_cached_result_used(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        try:
            service = GeocodingService(cache_path=tmp.name)
            service.cache.put("Hamburg, Germany", 53.55, 9.99, "nominatim")
            result = await service.geocode("Hamburg, Germany", access_token="fake")
            assert result == (53.55, 9.99)
        finally:
            service.close()
            os.unlink(tmp.name)

    @pytest.mark.asyncio
    async def test_nominatim_fallback(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        try:
            service = GeocodingService(cache_path=tmp.name)
            with patch.object(
                service, "_query_familysearch_places", return_value=None
            ), patch.object(service, "_query_nominatim", return_value=(53.55, 9.99)):
                result = await service.geocode("Hamburg, Germany", access_token="fake")
                assert result == (53.55, 9.99)
        finally:
            service.close()
            os.unlink(tmp.name)

    @pytest.mark.asyncio
    async def test_both_fail_returns_none(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        try:
            service = GeocodingService(cache_path=tmp.name)
            with patch.object(
                service, "_query_familysearch_places", return_value=None
            ), patch.object(service, "_query_nominatim", return_value=None):
                result = await service.geocode("Nowhere", access_token="fake")
                assert result is None
        finally:
            service.close()
            os.unlink(tmp.name)
