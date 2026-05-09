import re


def extract_year(date_string: str | None) -> int | None:
    """Extract a 4-digit year from a FamilySearch date string.

    Handles formats like:
    - "12 March 1845"
    - "1845-03-12"
    - "About 1845"
    - "Before March 1845"
    - "between 1840 and 1850" (returns first year)
    - "1845"

    Returns None if no year can be parsed.
    """
    if not date_string:
        return None

    matches = re.findall(r"\b(\d{4})\b", date_string)
    for match in matches:
        year = int(match)
        if 1000 <= year <= 2100:
            return year

    return None
