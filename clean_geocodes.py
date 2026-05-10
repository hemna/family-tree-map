#!/usr/bin/env python3
"""
Clean suspicious geocodes directly in the SQLite database.

Nullifies lat/lng for entries where:
- Pre-1492 ancestors geocoded to Americas, Oceania, or southern hemisphere
- Pre-600 ancestors outside Europe/Middle East/North Africa
- Place strings match non-geographic patterns ("At Sea", "Will", etc.)
- Birth and death are > 3000km apart for pre-1500 ancestors
"""
import math
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from app.database import get_connection, DB_PATH

BAD_PLACE_PATTERNS = [
    "at sea", "on sea", "indian ocean", "atlantic ocean", "pacific ocean",
    "at war", "in battle", "on pilgrimage", "will", "unknown",
    "of ", "probably", "possibly",
]


def extract_year_from_date(date_str):
    if not date_str:
        return None
    matches = re.findall(r'\b0*(\d{3,4})\b', date_str)
    for match in matches:
        year = int(match)
        if 100 <= year <= 2100:
            return year
    return None


def estimate_year_from_generation(generation):
    if generation is None:
        return None
    return 2000 - (generation * 25)


def is_bad_place(place_str):
    if not place_str:
        return False
    lower = place_str.lower().strip()
    if len(lower) <= 4 and not lower.isalpha():
        return True
    for pattern in BAD_PLACE_PATTERNS:
        if lower == pattern or lower.startswith(pattern):
            return True
    return False


def is_plausible_region(lat, lng, year):
    if year is None or year < 1492:
        if lng < -30:
            return False
        if lat < 0:
            return False
        if lng > 150:
            return False

    if year is not None and 1492 <= year < 1600:
        if lat < -10:
            return False

    if year is not None and year < 600:
        if lat < 10 or lat > 72:
            return False
        if lng < -15 or lng > 80:
            return False

    return True


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def clean_db():
    conn = get_connection()
    cursor = conn.execute("SELECT id, person_id, generation, birth_date_original, birth_date_year, birth_place, birth_lat, birth_lng, death_date_original, death_date_year, death_place, death_lat, death_lng FROM ancestors")

    fixed = 0
    batch = []

    for row in cursor.fetchall():
        row = dict(row)
        aid = row["id"]
        pid = row["person_id"]
        gen = row["generation"]

        # Determine year
        year = row["birth_date_year"] or row["death_date_year"]
        if year is None:
            year = extract_year_from_date(row["birth_date_original"])
        if year is None:
            year = extract_year_from_date(row["death_date_original"])
        if year is None:
            year = estimate_year_from_generation(gen)

        updates = {}

        # Check birth
        if row["birth_lat"] is not None:
            if is_bad_place(row["birth_place"]):
                updates["birth_lat"] = None
                updates["birth_lng"] = None
            elif not is_plausible_region(row["birth_lat"], row["birth_lng"], year):
                updates["birth_lat"] = None
                updates["birth_lng"] = None

        # Check death
        if row["death_lat"] is not None:
            if is_bad_place(row["death_place"]):
                updates["death_lat"] = None
                updates["death_lng"] = None
            elif not is_plausible_region(row["death_lat"], row["death_lng"], year):
                updates["death_lat"] = None
                updates["death_lng"] = None

        # Check birth/death distance
        b_lat = updates.get("birth_lat", row["birth_lat"])
        b_lng = updates.get("birth_lng", row["birth_lng"])
        d_lat = updates.get("death_lat", row["death_lat"])
        d_lng = updates.get("death_lng", row["death_lng"])

        if b_lat is not None and d_lat is not None:
            if year is None or year < 1500:
                dist = haversine(b_lat, b_lng, d_lat, d_lng)
                if dist > 3000:
                    updates["death_lat"] = None
                    updates["death_lng"] = None

        if updates:
            set_clauses = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [aid, pid]
            batch.append((f"UPDATE ancestors SET {set_clauses} WHERE id = ? AND person_id = ?", values))
            fixed += 1

        if len(batch) >= 1000:
            for sql, vals in batch:
                conn.execute(sql, vals)
            conn.commit()
            print(f"  Cleaned {fixed} so far...", flush=True)
            batch = []

    # Final batch
    for sql, vals in batch:
        conn.execute(sql, vals)
    conn.commit()
    conn.close()

    print(f"\nTotal cleaned: {fixed} bad geocodes nullified in database")


if __name__ == "__main__":
    print(f"Cleaning geocodes in {DB_PATH}...")
    clean_db()
