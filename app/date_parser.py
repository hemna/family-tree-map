import re


def extract_year(date_string: str | None) -> int | None:
    """Extract a year from a FamilySearch date string.

    Handles formats like:
    - "12 March 1845"
    - "1845-03-12"
    - "About 1845"
    - "Before March 1845"
    - "between 1840 and 1850" (returns first year)
    - "1845"
    - "974" (3-digit year)
    - "0389" (leading zero)

    Returns None for BC dates and unparseable strings.
    """
    if not date_string:
        return None

    # Skip BC dates entirely
    if "BC" in date_string.upper() or "B.C." in date_string.upper():
        return None

    # First try 4-digit years
    matches = re.findall(r"\b(\d{4})\b", date_string)
    for match in matches:
        year = int(match)
        if 100 <= year <= 2026:
            return year

    # Then try 3-digit years (with optional leading zeros)
    matches = re.findall(r"\b0*(\d{3,4})\b", date_string)
    for match in matches:
        year = int(match)
        if 100 <= year <= 2026:
            return year

    return None
