from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.conversation_models import (
    TravelLocation,
    TravelLocationSource,
)
from app.open_meteo import search_sri_lankan_locations


ADMINISTRATIVE_SEAT_FEATURE_PREFIXES = (
    "PPLC",
    "PPLA",
)

GENERIC_LOCALITY_SUFFIXES = (
    " city",
    " municipality",
    " town",
)


class LocationResolutionStatus(str, Enum):
    VERIFIED = "verified"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "notFound"


@dataclass(frozen=True, slots=True)
class LocationResolution:
    status: LocationResolutionStatus
    location: TravelLocation | None = None
    candidates: tuple[str, ...] = ()

    @property
    def is_verified(self) -> bool:
        return (
            self.status is LocationResolutionStatus.VERIFIED
            and self.location is not None
            and self.location.is_route_ready
        )


async def resolve_sri_lankan_location(
    query: str,
) -> LocationResolution:
    normalized_query = query.strip()

    if len(normalized_query) < 2:
        return LocationResolution(
            status=LocationResolutionStatus.NOT_FOUND,
        )

    results = await search_sri_lankan_locations(
        normalized_query,
        limit=8,
    )

    return resolve_location_results(
        query=normalized_query,
        results=results,
    )


def resolve_location_results(
    *,
    query: str,
    results: list[dict[str, Any]],
) -> LocationResolution:
    normalized_query = _normalize_location_text(query)
    locality_query, qualifiers = _query_parts(normalized_query)

    valid_results = [
        result
        for result in results
        if _is_valid_result(result) and _is_sri_lankan_result(result)
    ]

    if not valid_results:
        return LocationResolution(
            status=LocationResolutionStatus.NOT_FOUND,
        )

    scored_results = [
        (result, evidence)
        for result in valid_results
        if (
            evidence := _match_evidence(
                locality_query=locality_query,
                qualifiers=qualifiers,
                result=result,
            )
        )
        is not None
    ]

    corroborated_results = [
        (result, evidence)
        for result, evidence in scored_results
        if evidence[0] > 0
    ]

    if corroborated_results:
        best_evidence = max(
            evidence for _, evidence in corroborated_results
        )
        best_results = [
            result
            for result, evidence in corroborated_results
            if evidence == best_evidence
        ]
    else:
        best_results = []

    if len(best_results) == 1:
        return LocationResolution(
            status=LocationResolutionStatus.VERIFIED,
            location=_build_travel_location(best_results[0]),
        )

    candidate_results = (
        [result for result, _ in scored_results]
        if scored_results
        else valid_results
    )

    return LocationResolution(
        status=LocationResolutionStatus.AMBIGUOUS,
        candidates=_unique_candidate_labels(candidate_results),
    )


def _build_travel_location(
    result: dict[str, Any],
) -> TravelLocation:
    provider_id = result.get("id")

    return TravelLocation(
        display_name=str(result["displayName"]),
        locality_name=_optional_text(result.get("name")),
        source=TravelLocationSource.SEARCHED,
        latitude=float(result["latitude"]),
        longitude=float(result["longitude"]),
        provider_place_id=(str(provider_id) if provider_id is not None else None),
        country_code="LK",
        admin1=_optional_text(result.get("admin1")),
        admin2=_optional_text(result.get("admin2")),
        admin3=_optional_text(result.get("admin3")),
        admin4=_optional_text(result.get("admin4")),
        feature_code=_optional_text(
            result.get("featureCode") or result.get("feature_code")
        ),
        population=_population_or_none(result.get("population")),
        verified=True,
    )


def _is_valid_result(
    result: dict[str, Any],
) -> bool:
    display_name = str(result.get("displayName") or "").strip()

    latitude = result.get("latitude")
    longitude = result.get("longitude")

    return (
        bool(display_name)
        and isinstance(latitude, (int, float))
        and not isinstance(latitude, bool)
        and isinstance(longitude, (int, float))
        and not isinstance(longitude, bool)
        and math.isfinite(float(latitude))
        and math.isfinite(float(longitude))
        and -90 <= float(latitude) <= 90
        and -180 <= float(longitude) <= 180
    )


def _is_sri_lankan_result(
    result: dict[str, Any],
) -> bool:
    country_code = str(
        result.get("countryCode") or result.get("country_code") or ""
    ).strip()

    return country_code.upper() == "LK"


def _match_evidence(
    *,
    locality_query: str,
    qualifiers: tuple[str, ...],
    result: dict[str, Any],
) -> tuple[int, int, int] | None:
    if not locality_query:
        return None

    name = _normalize_location_text(str(result.get("name") or ""))
    admin_values = tuple(
        value
        for field in ("admin1", "admin2", "admin3", "admin4")
        if (value := _normalize_location_text(str(result.get(field) or "")))
    )

    if qualifiers and not all(
        qualifier in admin_values or qualifier == "sri lanka"
        for qualifier in qualifiers
    ):
        return None

    if name == locality_query:
        name_evidence = 4
    elif _without_generic_locality_suffix(name) == locality_query:
        name_evidence = 3
    elif locality_query in admin_values:
        name_evidence = 2
    elif name.startswith(f"{locality_query} "):
        name_evidence = 1
    else:
        return None

    exact_admin_match = locality_query in admin_values
    feature_code = str(
        result.get("featureCode") or result.get("feature_code") or ""
    ).strip().upper()
    administrative_seat = feature_code.startswith(
        ADMINISTRATIVE_SEAT_FEATURE_PREFIXES
    )
    population = _population_or_none(result.get("population"))

    if qualifiers:
        corroboration = 4
    elif exact_admin_match:
        corroboration = 3
    elif administrative_seat:
        corroboration = 2
    elif population is not None and population > 0:
        corroboration = 1
    else:
        corroboration = 0

    return (
        corroboration,
        1 if population is not None and population > 0 else 0,
        name_evidence,
    )


def _query_parts(
    normalized_query: str,
) -> tuple[str, tuple[str, ...]]:
    parts = tuple(
        part.strip()
        for part in normalized_query.split(",")
        if part.strip()
    )

    if not parts:
        return "", ()

    return parts[0], parts[1:]


def _without_generic_locality_suffix(
    value: str,
) -> str:
    for suffix in GENERIC_LOCALITY_SUFFIXES:
        if value.endswith(suffix):
            return value[: -len(suffix)].strip()

    return value


def _optional_text(
    value: Any,
) -> str | None:
    normalized = str(value or "").strip()

    return normalized or None


def _population_or_none(
    value: Any,
) -> int | None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        return None

    return value


def _unique_candidate_labels(
    results: list[dict[str, Any]],
) -> tuple[str, ...]:
    labels: list[str] = []
    seen: set[str] = set()

    for result in results:
        label = str(result.get("displayName") or "").strip()

        comparison_value = label.casefold()

        if not label or comparison_value in seen:
            continue

        seen.add(comparison_value)
        labels.append(label)

    return tuple(labels)


def _normalize_location_text(
    value: str,
) -> str:
    normalized = unicodedata.normalize(
        "NFKC",
        value,
    ).casefold()

    normalized = re.sub(
        r"[^\w\s,]",
        " ",
        normalized,
    )

    return re.sub(r"\s+", " ", normalized).strip()
