#!/usr/bin/env python3
"""
Clean suspicious geocodes from ancestor data files.

Nullifies lat/lng for entries where:
- Birth and death are > 3000km apart for people born before 1500
- Place string matches known non-geographic patterns ("At Sea", "Will", etc.)
- Pre-1500 ancestors geocoded to Americas, Oceania, or other impossible regions
"""
import json
import math
import sys
from pathlib import Path

# Non-geographic place strings that should never be geocoded
BAD_PLACE_PATTERNS = [
    "at sea", "on sea", "indian ocean", "atlantic ocean", "pacific ocean",
    "at war", "in battle", "on pilgrimage", "will", "unknown",
    "of ", "probably", "possibly",
]


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


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
    """Check if a geocode is in a plausible region for the given year."""
    # Before 1492 (Columbus): Americas, Oceania are impossible for European lineages
    if year is None or year < 1492:
        # Western hemisphere
        if lng < -30:
            return False
        # Southern hemisphere (no European ancestors lived below equator before 1492)
        if lat < 0:
            return False
        # Oceania/Australia/Pacific
        if lng > 150:
            return False

    # Between 1492 and 1600: very few Europeans in southern hemisphere
    if year is not None and 1492 <= year < 1600:
        if lat < -10:
            return False

    # Before 600 AD: should be Europe, Middle East, or North Africa
    if year is not None and year < 600:
        if lat < 10 or lat > 72:
            return False
        if lng < -15 or lng > 80:
            return False

    return True


def extract_year_from_date(date_str):
    """Extract year from date string, handling leading zeros like '0389'."""
    import re
    if not date_str:
        return None
    # Match 3-4 digit numbers (with optional leading zeros), avoiding day numbers (1-31)
    matches = re.findall(r'\b0*(\d{3,4})\b', date_str)
    for match in matches:
        year = int(match)
        if 1 <= year <= 2100:
            return year
    return None


def estimate_year_from_generation(generation):
    """Rough estimate: ~25 years per generation from present (2000)."""
    if generation is None:
        return None
    return 2000 - (generation * 25)


def clean_file(filepath):
    data = json.loads(filepath.read_text())
    fixed = 0

    for ancestor in data:
        birth = ancestor.get("birth") or {}
        death = ancestor.get("death") or {}

        # Determine approximate year for this ancestor (multiple strategies)
        year = birth.get("date_year") or death.get("date_year")
        if year is None:
            year = extract_year_from_date(birth.get("date_original"))
        if year is None:
            year = extract_year_from_date(death.get("date_original"))
        if year is None:
            year = estimate_year_from_generation(ancestor.get("generation"))

        # Check for bad place strings
        for event in [birth, death]:
            if event.get("lat") is not None and is_bad_place(event.get("place", "")):
                event["lat"] = None
                event["lng"] = None
                fixed += 1

        # Check for implausible regions given the year
        for event in [birth, death]:
            if event.get("lat") is not None:
                if not is_plausible_region(event["lat"], event["lng"], year):
                    event["lat"] = None
                    event["lng"] = None
                    fixed += 1

        # Check for suspiciously distant birth/death (pre-1500, > 3000km)
        if (birth.get("lat") is not None and death.get("lat") is not None):
            if year is None or year < 1500:
                dist = haversine(birth["lat"], birth["lng"], death["lat"], death["lng"])
                if dist > 3000:
                    death["lat"] = None
                    death["lng"] = None
                    fixed += 1

    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return len(data), fixed


if __name__ == "__main__":
    data_dir = Path("data")
    total_fixed = 0

    for json_file in sorted(data_dir.glob("*.json")):
        if json_file.name in ("manifest.json", "geocache.json"):
            continue
        count, fixed = clean_file(json_file)
        print(f"  {json_file.name}: {count} ancestors, {fixed} geocodes cleaned")
        total_fixed += fixed

    print(f"\nTotal cleaned: {total_fixed} bad geocodes nullified")
