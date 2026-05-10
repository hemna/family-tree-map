# Family Tree Map & Timeline

Visualize your family ancestry on an interactive Leaflet map with marker clustering, a timeline scrubber, lineage tracing, and ancestor search. Supports multiple people side-by-side with common ancestor detection.

## Prerequisites

- Python 3.11+
- A FamilySearch.org account (free)

## Setup

1. Clone and install:
   ```bash
   cd family-tree-map
   pip install -e ".[dev]"
   ```

2. Run the app:
   ```bash
   uvicorn app.main:app --port 3000
   ```

3. Open http://localhost:3000 in your browser.

## Scraping Ancestry Data

The app uses a scraper to fetch your family tree from FamilySearch and store it in a local SQLite database. No API keys are needed — just your session cookie.

### Step 1: Get your FamilySearch session token

1. Log into [familysearch.org](https://www.familysearch.org) in your browser
2. Open browser DevTools (F12 or Cmd+Option+I)
3. Go to **Application** → **Cookies** → `https://www.familysearch.org`
4. Find the cookie named `fssessionid`
5. Copy its value (looks like `p0-RzR2l~Eh4dt.D~RQ~VNPcJp`)

### Step 2: Run the scraper

**Scrape your own tree (paternal side):**
```bash
python scrape_ancestry.py --token "YOUR_FSSESSIONID" --side paternal
```

**Scrape your own tree (maternal side):**
```bash
python scrape_ancestry.py --token "YOUR_FSSESSIONID" --side maternal
```

**Scrape someone else's tree (by FamilySearch person ID):**
```bash
python scrape_ancestry.py --token "YOUR_FSSESSIONID" --person-id XXXX-YYY --side paternal
```

The person ID is in the URL when viewing someone on FamilySearch:
`https://www.familysearch.org/tree/person/details/XXXX-YYY`

### Scraper Options

| Option | Description |
|--------|-------------|
| `--token TOKEN` | Your `fssessionid` cookie value (required) |
| `--side paternal\|maternal` | Which parent's lineage to follow (prompts if omitted) |
| `--person-id ID` | Start from a specific person instead of yourself |
| `--max N` | Maximum ancestors to fetch (default: unlimited) |
| `--client-id ID` | Use OAuth flow instead of manual token |

### How it works

- Fetches ancestors using breadth-first search (follows both parents at each generation)
- Each ancestor is inserted directly into `data/family_tree.db` (SQLite)
- Geocodes birth/death places using FamilySearch Places API + Nominatim fallback
- Commits to database every 50 ancestors (crash-safe)
- Minimal RAM usage — no data accumulated in memory
- The app reads from the same database, so new ancestors appear on refresh

### Notes

- The `fssessionid` token expires after a few hours. If the scraper stops with auth errors, get a fresh token.
- Nominatim geocoding is rate-limited to 1 request/second. Large trees take time.
- FamilySearch's shared tree can be very deep (40+ generations for European lineages). The scraper will run until it exhausts all parent links.
- Run `python clean_geocodes.py` after scraping to remove implausible geocode results (e.g., pre-1492 ancestors placed in the Americas).

## Setting Up Multiple People

Edit `data/manifest.json` to define who appears in the app:

```json
{
  "people": [
    {
      "id": "person1",
      "name": "Your Name",
      "files": [],
      "familysearch_id": "XXXX-YYY"
    },
    {
      "id": "person2",
      "name": "Someone Else",
      "files": [],
      "familysearch_id": "ZZZZ-AAA"
    }
  ]
}
```

The `familysearch_id` must match the person ID used in the scraper's `--person-id` flag (or your own ID if scraping without `--person-id`). The scraper uses this to link the data to the correct person in the database.

## Migrating from JSON to SQLite

If you have existing JSON data files from an older version of the scraper:

```bash
python migrate_to_sqlite.py
```

This reads `data/manifest.json` and imports all referenced JSON files into `data/family_tree.db`.

## Features

- **Interactive map** with Leaflet + OpenStreetMap tiles
- **Marker clustering** for performance with 100k+ ancestors
- **Timeline slider** to filter by year range
- **Ancestor search** with server-side full-text matching
- **Lineage panel** — click a pin to see the path from you to that ancestor
- **Birth/death migration lines** — dotted line between birth and death locations
- **Multiple people** — switch between family trees via dropdown
- **Common ancestors view** — find and display shared ancestors between people
- **Notable ancestors panel** — browse titled/royal ancestors
- **Paternal/maternal toggles** — show/hide by lineage side
- **Live scrape status** — see scraping progress in the app

## Running Tests

```bash
pytest tests/ -v
```

## Tech Stack

- **Backend:** Python, FastAPI, SQLite, Jinja2
- **Frontend:** Leaflet.js, Leaflet.markercluster, noUiSlider, vanilla JS
- **Geocoding:** FamilySearch Places API + Nominatim/OpenStreetMap
- **Data:** SQLite with WAL mode for concurrent read/write
