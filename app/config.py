import os


class Settings:
    FAMILYSEARCH_CLIENT_ID: str = os.environ.get("FAMILYSEARCH_CLIENT_ID", "")
    FAMILYSEARCH_CLIENT_SECRET: str = os.environ.get("FAMILYSEARCH_CLIENT_SECRET", "")
    FAMILYSEARCH_REDIRECT_URI: str = os.environ.get(
        "FAMILYSEARCH_REDIRECT_URI", "http://localhost:8000/callback"
    )
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    FAMILYSEARCH_BASE_URL: str = "https://api.familysearch.org"
    FAMILYSEARCH_AUTH_URL: str = "https://ident.familysearch.org/cis-web/oauth2/v3"
    NOMINATIM_BASE_URL: str = "https://nominatim.openstreetmap.org"
    MAX_ANCESTORS: int = 500


settings = Settings()
