"""SQLite database module for ancestor storage.

Provides the database schema and query interface for ancestor data.
Replaces the JSON file approach for better performance with large datasets.
"""
import sqlite3
from pathlib import Path
from typing import Any


DB_PATH = Path("data/family_tree.db")


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Get a database connection with row factory enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent read/write
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    """Create database tables if they don't exist."""
    conn = get_connection(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS people (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            familysearch_id TEXT
        );

        CREATE TABLE IF NOT EXISTS ancestors (
            id TEXT NOT NULL,
            person_id TEXT NOT NULL,
            name TEXT NOT NULL,
            gender TEXT,
            relationship TEXT,
            generation INTEGER,
            side TEXT,
            child_id TEXT,
            birth_date_original TEXT,
            birth_date_year INTEGER,
            birth_place TEXT,
            birth_lat REAL,
            birth_lng REAL,
            death_date_original TEXT,
            death_date_year INTEGER,
            death_place TEXT,
            death_lat REAL,
            death_lng REAL,
            familysearch_url TEXT,
            PRIMARY KEY (id, person_id),
            FOREIGN KEY (person_id) REFERENCES people(id)
        );

        CREATE INDEX IF NOT EXISTS idx_ancestors_person_id ON ancestors(person_id);
        CREATE INDEX IF NOT EXISTS idx_ancestors_person_side ON ancestors(person_id, side);
        CREATE INDEX IF NOT EXISTS idx_ancestors_birth_year ON ancestors(birth_date_year);
        CREATE INDEX IF NOT EXISTS idx_ancestors_death_year ON ancestors(death_date_year);
        CREATE INDEX IF NOT EXISTS idx_ancestors_name ON ancestors(name COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS idx_ancestors_generation ON ancestors(person_id, generation);
        CREATE INDEX IF NOT EXISTS idx_ancestors_child_id ON ancestors(child_id, person_id);

        -- Spouses and marriages
        CREATE TABLE IF NOT EXISTS spouses (
            ancestor_id TEXT NOT NULL,
            person_id TEXT NOT NULL,
            spouse_id TEXT,
            spouse_name TEXT,
            marriage_date_original TEXT,
            marriage_date_year INTEGER,
            marriage_place TEXT,
            marriage_lat REAL,
            marriage_lng REAL,
            PRIMARY KEY (ancestor_id, person_id, spouse_id),
            FOREIGN KEY (ancestor_id, person_id) REFERENCES ancestors(id, person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_spouses_person ON spouses(person_id);
        CREATE INDEX IF NOT EXISTS idx_spouses_ancestor ON spouses(ancestor_id, person_id);

        -- Siblings (children in the same family)
        CREATE TABLE IF NOT EXISTS siblings (
            ancestor_id TEXT NOT NULL,
            person_id TEXT NOT NULL,
            sibling_id TEXT NOT NULL,
            sibling_name TEXT,
            PRIMARY KEY (ancestor_id, person_id, sibling_id),
            FOREIGN KEY (ancestor_id, person_id) REFERENCES ancestors(id, person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_siblings_ancestor ON siblings(ancestor_id, person_id);

        -- Facts (occupations, residences, military, etc.)
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ancestor_id TEXT NOT NULL,
            person_id TEXT NOT NULL,
            fact_type TEXT NOT NULL,
            date_original TEXT,
            date_year INTEGER,
            place TEXT,
            value TEXT,
            FOREIGN KEY (ancestor_id, person_id) REFERENCES ancestors(id, person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_facts_ancestor ON facts(ancestor_id, person_id);
        CREATE INDEX IF NOT EXISTS idx_facts_type ON facts(fact_type);

        -- Source records attached to persons
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ancestor_id TEXT NOT NULL,
            person_id TEXT NOT NULL,
            title TEXT,
            citation TEXT,
            record_type TEXT,
            url TEXT,
            FOREIGN KEY (ancestor_id, person_id) REFERENCES ancestors(id, person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_sources_ancestor ON sources(ancestor_id, person_id);

        -- Geocoding cache
        CREATE TABLE IF NOT EXISTS geocache (
            place_string TEXT PRIMARY KEY,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def upsert_person(conn: sqlite3.Connection, person_id: str, name: str, familysearch_id: str = "") -> None:
    """Insert or update a person entry."""
    conn.execute(
        "INSERT OR REPLACE INTO people (id, name, familysearch_id) VALUES (?, ?, ?)",
        (person_id, name, familysearch_id),
    )
    conn.commit()


def upsert_ancestor(conn: sqlite3.Connection, person_id: str, ancestor: dict) -> None:
    """Insert or update a single ancestor record."""
    birth = ancestor.get("birth") or {}
    death = ancestor.get("death") or {}
    conn.execute(
        """INSERT OR REPLACE INTO ancestors
           (id, person_id, name, gender, relationship, generation, side, child_id,
            birth_date_original, birth_date_year, birth_place, birth_lat, birth_lng,
            death_date_original, death_date_year, death_place, death_lat, death_lng,
            familysearch_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ancestor["id"],
            person_id,
            ancestor.get("name", "Unknown"),
            ancestor.get("gender"),
            ancestor.get("relationship"),
            ancestor.get("generation"),
            ancestor.get("side"),
            ancestor.get("child_id"),
            birth.get("date_original"),
            birth.get("date_year"),
            birth.get("place"),
            birth.get("lat"),
            birth.get("lng"),
            death.get("date_original"),
            death.get("date_year"),
            death.get("place"),
            death.get("lat"),
            death.get("lng"),
            ancestor.get("familysearch_url"),
        ),
    )


def bulk_upsert_ancestors(conn: sqlite3.Connection, person_id: str, ancestors: list[dict]) -> None:
    """Bulk insert/update ancestors for a person."""
    for ancestor in ancestors:
        upsert_ancestor(conn, person_id, ancestor)
    conn.commit()


def upsert_spouse(conn: sqlite3.Connection, person_id: str, ancestor_id: str,
                  spouse_id: str, spouse_name: str,
                  marriage_date: str | None = None, marriage_year: int | None = None,
                  marriage_place: str | None = None,
                  marriage_lat: float | None = None, marriage_lng: float | None = None) -> None:
    """Insert or update a spouse/marriage record."""
    conn.execute(
        """INSERT OR REPLACE INTO spouses
           (ancestor_id, person_id, spouse_id, spouse_name,
            marriage_date_original, marriage_date_year, marriage_place, marriage_lat, marriage_lng)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ancestor_id, person_id, spouse_id, spouse_name,
         marriage_date, marriage_year, marriage_place, marriage_lat, marriage_lng),
    )


def upsert_sibling(conn: sqlite3.Connection, person_id: str, ancestor_id: str,
                   sibling_id: str, sibling_name: str | None = None) -> None:
    """Insert or update a sibling record."""
    conn.execute(
        """INSERT OR REPLACE INTO siblings
           (ancestor_id, person_id, sibling_id, sibling_name)
           VALUES (?, ?, ?, ?)""",
        (ancestor_id, person_id, sibling_id, sibling_name),
    )


def insert_fact(conn: sqlite3.Connection, person_id: str, ancestor_id: str,
                fact_type: str, date_original: str | None = None,
                date_year: int | None = None, place: str | None = None,
                value: str | None = None) -> None:
    """Insert a fact record (occupation, residence, military, etc.)."""
    # Avoid duplicates by checking if same fact already exists
    existing = conn.execute(
        """SELECT id FROM facts WHERE ancestor_id = ? AND person_id = ?
           AND fact_type = ? AND COALESCE(date_original,'') = COALESCE(?,'')""",
        (ancestor_id, person_id, fact_type, date_original),
    ).fetchone()
    if not existing:
        conn.execute(
            """INSERT INTO facts (ancestor_id, person_id, fact_type, date_original, date_year, place, value)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ancestor_id, person_id, fact_type, date_original, date_year, place, value),
        )


def insert_source(conn: sqlite3.Connection, person_id: str, ancestor_id: str,
                  title: str | None = None, citation: str | None = None,
                  record_type: str | None = None, url: str | None = None) -> None:
    """Insert a source record."""
    existing = conn.execute(
        """SELECT id FROM sources WHERE ancestor_id = ? AND person_id = ?
           AND COALESCE(title,'') = COALESCE(?,'') AND COALESCE(url,'') = COALESCE(?,'')""",
        (ancestor_id, person_id, title, url),
    ).fetchone()
    if not existing:
        conn.execute(
            """INSERT INTO sources (ancestor_id, person_id, title, citation, record_type, url)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ancestor_id, person_id, title, citation, record_type, url),
        )


def get_ancestors(
    conn: sqlite3.Connection,
    person_id: str,
    side: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    search: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    """Query ancestors with optional filters."""
    query = "SELECT * FROM ancestors WHERE person_id = ?"
    params: list[Any] = [person_id]

    if side:
        query += " AND side = ?"
        params.append(side)

    if year_min is not None:
        query += " AND (birth_date_year >= ? OR death_date_year >= ?)"
        params.extend([year_min, year_min])

    if year_max is not None:
        query += " AND (birth_date_year <= ? OR death_date_year <= ?)"
        params.extend([year_max, year_max])

    if search:
        query += " AND name LIKE ?"
        params.append(f"%{search}%")

    query += " ORDER BY generation, name"

    if limit:
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    cursor = conn.execute(query, params)
    return [_row_to_dict(row) for row in cursor.fetchall()]


def get_ancestor_count(conn: sqlite3.Connection, person_id: str) -> int:
    """Get total ancestor count for a person."""
    cursor = conn.execute(
        "SELECT COUNT(*) FROM ancestors WHERE person_id = ?", (person_id,)
    )
    return cursor.fetchone()[0]


def get_common_ancestors(conn: sqlite3.Connection, person_ids: list[str]) -> list[dict]:
    """Find ancestors shared between all given people."""
    if len(person_ids) < 2:
        return []

    # Find IDs that appear for all people
    placeholders = ",".join(["?"] * len(person_ids))
    cursor = conn.execute(
        f"""SELECT id FROM ancestors
            WHERE person_id IN ({placeholders})
            GROUP BY id
            HAVING COUNT(DISTINCT person_id) = ?""",
        (*person_ids, len(person_ids)),
    )
    common_ids = [row[0] for row in cursor.fetchall()]

    if not common_ids:
        return []

    # Build result with relationship info from each person
    results = []
    id_placeholders = ",".join(["?"] * len(common_ids))

    for common_id in common_ids:
        rows = conn.execute(
            "SELECT * FROM ancestors WHERE id = ? AND person_id IN ({})".format(placeholders),
            (common_id, *person_ids),
        ).fetchall()

        if rows:
            base = _row_to_dict(rows[0])
            # Merge relationships from all people
            rels = []
            for row in rows:
                r = dict(row)
                pid = r["person_id"]
                rels.append(f"{pid}: {r['relationship']}")
            base["relationship"] = "<br>".join(rels)
            base["side"] = "common"
            results.append(base)

    return results


def get_lineage_path(conn: sqlite3.Connection, person_id: str, ancestor_id: str) -> list[dict]:
    """Trace the lineage path from an ancestor back to generation 1 via child_id."""
    path = []
    current_id = ancestor_id

    # Prevent infinite loops
    visited = set()
    while current_id and current_id not in visited:
        visited.add(current_id)
        cursor = conn.execute(
            "SELECT * FROM ancestors WHERE id = ? AND person_id = ?",
            (current_id, person_id),
        )
        row = cursor.fetchone()
        if not row:
            break
        ancestor = _row_to_dict(row)
        path.append({
            "id": ancestor["id"],
            "name": ancestor["name"],
            "relationship": ancestor["relationship"],
            "generation": ancestor["generation"],
            "familysearch_url": ancestor["familysearch_url"],
        })
        current_id = row["child_id"]

    path.reverse()
    return path


def search_ancestors(conn: sqlite3.Connection, person_id: str, query: str, limit: int = 15) -> list[dict]:
    """Search ancestors by name."""
    cursor = conn.execute(
        """SELECT * FROM ancestors
           WHERE person_id = ? AND name LIKE ?
           ORDER BY generation
           LIMIT ?""",
        (person_id, f"%{query}%", limit),
    )
    return [_row_to_dict(row) for row in cursor.fetchall()]


def get_year_range(conn: sqlite3.Connection, person_id: str) -> tuple[int | None, int | None]:
    """Get the min and max years for a person's ancestors."""
    cursor = conn.execute(
        """SELECT
            MIN(COALESCE(birth_date_year, death_date_year)),
            MAX(COALESCE(birth_date_year, death_date_year))
           FROM ancestors WHERE person_id = ?
           AND (birth_date_year IS NOT NULL OR death_date_year IS NOT NULL)""",
        (person_id,),
    )
    row = cursor.fetchone()
    return (row[0], row[1]) if row else (None, None)


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a database row to the ancestor dict format expected by the frontend."""
    r = dict(row)
    return {
        "id": r["id"],
        "name": r["name"],
        "gender": r["gender"],
        "relationship": r["relationship"],
        "generation": r["generation"],
        "side": r["side"],
        "child_id": r["child_id"],
        "birth": {
            "date_original": r["birth_date_original"],
            "date_year": r["birth_date_year"],
            "place": r["birth_place"],
            "lat": r["birth_lat"],
            "lng": r["birth_lng"],
        },
        "death": {
            "date_original": r["death_date_original"],
            "date_year": r["death_date_year"],
            "place": r["death_place"],
            "lat": r["death_lat"],
            "lng": r["death_lng"],
        },
        "familysearch_url": r["familysearch_url"],
    }
