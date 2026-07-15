import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ALLOWED_TOKENS = {"{YYYY}", "{YY}", "{MM}", "{DD}"}


def validate_pattern(pattern: str) -> str:
    pattern = pattern.strip().strip("/")
    if not pattern or os.path.isabs(pattern) or ".." in pattern.split("/"):
        raise ValueError("Pattern directory non valido")
    remaining = pattern
    for token in ALLOWED_TOKENS:
        remaining = remaining.replace(token, "")
    if "{" in remaining or "}" in remaining:
        raise ValueError("Token pattern supportati: {YYYY}, {YY}, {MM}, {DD}")
    if "{YYYY}" not in pattern and "{YY}" not in pattern:
        raise ValueError("Il pattern deve contenere l'anno")
    if "{MM}" not in pattern or "{DD}" not in pattern:
        raise ValueError("Il pattern deve contenere mese e giorno")
    return pattern


def partition_key(day: date) -> str:
    return day.isoformat()


def resolve_partition(root: str, pattern: str, day: date) -> str:
    relative = validate_pattern(pattern)
    values = {
        "{YYYY}": f"{day.year:04d}",
        "{YY}": f"{day.year % 100:02d}",
        "{MM}": f"{day.month:02d}",
        "{DD}": f"{day.day:02d}",
    }
    for token, value in values.items():
        relative = relative.replace(token, value)
    root = os.path.abspath(root)
    path = os.path.abspath(os.path.join(root, relative))
    if os.path.commonpath((root, path)) != root:
        raise ValueError("Il pattern esce dalla directory sorgente")
    return path


def dates_for_range(from_ts: float, to_ts: float, timezone_name: str) -> list[date]:
    tz = ZoneInfo(timezone_name)
    start = datetime.fromtimestamp(from_ts, tz).date()
    # L'estremo finale e esclusivo: mezzanotte appartiene al giorno successivo solo se superata.
    end = datetime.fromtimestamp(max(from_ts, to_ts - 0.001), tz).date()
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days
