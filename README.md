# Family Tree Map & Timeline

Visualize your family ancestry on an interactive map. Sign in with FamilySearch, choose a parental lineage, and see your ancestors' birth and death locations plotted on a Leaflet map with a time-range slider.

## Prerequisites

- Python 3.11+
- FamilySearch developer account and API keys

## Setup

1. Clone and install:
   ```bash
   cd family-tree-map
   pip install -e ".[dev]"
   ```

2. Copy `.env.example` to `.env` and fill in your FamilySearch credentials:
   ```bash
   cp .env.example .env
   ```

3. Run the app:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

4. Open http://localhost:8000 in your browser.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `FAMILYSEARCH_CLIENT_ID` | Your FamilySearch app key |
| `FAMILYSEARCH_CLIENT_SECRET` | Your FamilySearch app secret |
| `FAMILYSEARCH_REDIRECT_URI` | OAuth callback URL (default: `http://localhost:8000/callback`) |
| `SECRET_KEY` | Random string for session signing |

## Running Tests

```bash
pytest tests/ -v
```

## How It Works

1. Sign in with your FamilySearch account
2. Select father's or mother's side
3. App fetches your ancestry recursively (up to 500 ancestors)
4. Places are geocoded using FamilySearch Places API + Nominatim
5. Map shows birth (green) and death (red) pins
6. Timeline slider filters pins by year range
