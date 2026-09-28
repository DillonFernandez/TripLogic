from __future__ import annotations

import re
from datetime import time

NUMBER_WORDS: dict[str, float] = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "half": 0.5,
    "an": 1,
    "a": 1,
}

NUMBER_PATTERN = r"(?:\d+(?:\.\d+)?|" + "|".join(NUMBER_WORDS) + r")"


def parse_duration_minutes(
    value: str | None,
) -> int | None:
    if value is None:
        return None

    normalized = value.strip().casefold()

    if not normalized:
        return None

    hours = _extract_quantity(
        normalized,
        unit_pattern=r"hours?|hrs?|hr",
    )

    minutes = _extract_quantity(
        normalized,
        unit_pattern=r"minutes?|mins?|min",
    )

    if hours is None and minutes is None:
        return None

    total_minutes = int(round((hours or 0) * 60 + (minutes or 0)))

    if total_minutes <= 0:
        return None

    return total_minutes


def calculate_time_window_minutes(
    *,
    start_time: time | None,
    end_time: time | None,
) -> int | None:
    if start_time is None or end_time is None:
        return None

    start_minutes = start_time.hour * 60 + start_time.minute

    end_minutes = end_time.hour * 60 + end_time.minute

    duration = end_minutes - start_minutes

    if duration <= 0:
        raise ValueError("dailyEndTime must be after dailyStartTime.")

    return duration


def _extract_quantity(
    value: str,
    *,
    unit_pattern: str,
) -> float | None:
    match = re.search(
        (rf"\b({NUMBER_PATTERN})" rf"(?:\s+(?:a|an))?" rf"\s*(?:{unit_pattern})\b"),
        value,
    )

    if match is None:
        return None

    raw_quantity = match.group(1)

    if raw_quantity in NUMBER_WORDS:
        return NUMBER_WORDS[raw_quantity]

    try:
        return float(raw_quantity)
    except ValueError:
        return None
