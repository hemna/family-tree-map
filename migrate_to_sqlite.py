#!/usr/bin/env python3
"""Migrate existing JSON ancestor data files into SQLite database."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from app.database import init_db, get_connection, upsert_person, bulk_upsert_ancestors, DB_PATH


def migrate():
    data_dir = Path("data")
    manifest_file = data_dir / "manifest.json"

    if not manifest_file.exists():
        print("ERROR: data/manifest.json not found")
        sys.exit(1)

    manifest = json.loads(manifest_file.read_text())

    # Initialize database
    print(f"Initializing database at {DB_PATH}...")
    init_db()
    conn = get_connection()

    for person in manifest.get("people", []):
        person_id = person["id"]
        name = person["name"]
        fs_id = person.get("familysearch_id", "")
        files = person.get("files", [])
        if not files and person.get("file"):
            files = [person["file"]]

        print(f"\nMigrating {name} ({person_id})...")
        upsert_person(conn, person_id, name, fs_id)

        total = 0
        seen_ids = set()
        for f in files:
            data_file = data_dir / f
            if not data_file.exists():
                print(f"  Skipping {f} (not found)")
                continue

            print(f"  Loading {f}...")
            try:
                ancestors = json.loads(data_file.read_text())
            except json.JSONDecodeError:
                print(f"  ERROR: Could not parse {f}")
                continue

            # Dedup within this person
            new_ancestors = []
            for a in ancestors:
                if a["id"] not in seen_ids:
                    seen_ids.add(a["id"])
                    new_ancestors.append(a)

            # Bulk insert in batches of 1000
            batch_size = 1000
            for i in range(0, len(new_ancestors), batch_size):
                batch = new_ancestors[i:i + batch_size]
                bulk_upsert_ancestors(conn, person_id, batch)
                total += len(batch)
                print(f"    Inserted {total} ancestors...", end="\r")

            print(f"    Inserted {total} ancestors from {f}")

        print(f"  Total for {name}: {total} ancestors")

    # Print summary
    cursor = conn.execute("SELECT person_id, COUNT(*) FROM ancestors GROUP BY person_id")
    print("\n" + "=" * 40)
    print("Migration complete!")
    print("=" * 40)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} ancestors")

    db_size = DB_PATH.stat().st_size / (1024 * 1024)
    print(f"\nDatabase size: {db_size:.1f} MB")
    print(f"Location: {DB_PATH.resolve()}")

    conn.close()


if __name__ == "__main__":
    migrate()
