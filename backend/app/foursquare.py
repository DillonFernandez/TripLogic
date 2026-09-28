import asyncio
import math
import re
import time
import unicodedata
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import get_settings
from app.recommendation_models import (
    RecommendationOpeningHours,
    RecommendationOpeningInterval,
    RecommendationPlaceMetadata,
)

FOURSQUARE_BASE_URL = "https://places-api.foursquare.com"

FOURSQUARE_SEARCH_URL = f"{FOURSQUARE_BASE_URL}/places/search"

FOURSQUARE_API_VERSION = "2025-06-17"

DEFAULT_SEARCH_RADIUS_METERS = 15_000
MAXIMUM_SEARCH_RADIUS_METERS = 100_000
MAXIMUM_SEARCH_RESULTS = 50
MAXIMUM_CATEGORY_ID_LENGTH = 64
MAXIMUM_REQUEST_ATTEMPTS = 3
MAXIMUM_RETRY_AFTER_SECONDS = 5.0
PREMIUM_METADATA_CAPABILITY_TTL_SECONDS = 15 * 60

RETRY_BACKOFF_SECONDS = (
    0.25,
    0.5,
)

RETRYABLE_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}

CATEGORY_ID_PATTERN = re.compile(r"^[A-Za-z0-9]+$")

SUPPORTED_SORT_OPTIONS = {
    "RELEVANCE",
    "RATING",
    "DISTANCE",
    "POPULARITY",
}

BASE_SEARCH_FIELDS = (
    "fsq_place_id,name,categories,location,latitude,longitude,distance"
)

APPROVED_PREMIUM_SEARCH_FIELDS = (
    "rating",
    "hours",
)

SEARCH_FIELDS = ",".join(
    (
        BASE_SEARCH_FIELDS,
        *APPROVED_PREMIUM_SEARCH_FIELDS,
    )
)

EARTH_RADIUS_METERS = 6_371_000.0

_PREMIUM_CAPABILITY_UNKNOWN = "unknown"
_PREMIUM_CAPABILITY_AVAILABLE = "available"
_PREMIUM_CAPABILITY_UNAVAILABLE = "unavailable"

_premium_metadata_capability = _PREMIUM_CAPABILITY_UNKNOWN
_premium_metadata_capability_checked_at: float | None = None
_premium_metadata_capability_lock = asyncio.Lock()


class _PremiumMetadataAccessError(Exception):
    """An explicit provider denial of the approved Premium metadata fields."""


class _AmbiguousPremiumMetadataRateLimitError(Exception):
    """A first-probe 429 that requires one base-field capability check."""


def _reset_premium_metadata_capability() -> None:
    """Forget the process-local capability observation."""

    global _premium_metadata_capability
    global _premium_metadata_capability_checked_at

    _premium_metadata_capability = _PREMIUM_CAPABILITY_UNKNOWN
    _premium_metadata_capability_checked_at = None


def _current_premium_metadata_capability() -> str:
    global _premium_metadata_capability
    global _premium_metadata_capability_checked_at

    if (
        _premium_metadata_capability == _PREMIUM_CAPABILITY_UNAVAILABLE
        and _premium_metadata_capability_checked_at is not None
        and time.monotonic() - _premium_metadata_capability_checked_at
        >= PREMIUM_METADATA_CAPABILITY_TTL_SECONDS
    ):
        _premium_metadata_capability = _PREMIUM_CAPABILITY_UNKNOWN
        _premium_metadata_capability_checked_at = None

    return _premium_metadata_capability


def _mark_premium_metadata_capability(
    capability: str,
) -> None:
    global _premium_metadata_capability
    global _premium_metadata_capability_checked_at

    _premium_metadata_capability = capability
    _premium_metadata_capability_checked_at = time.monotonic()


def _is_number(
    value: Any,
) -> bool:
    """Return true for integers and floats, excluding booleans."""

    return isinstance(
        value,
        (int, float),
    ) and not isinstance(
        value,
        bool,
    )


def _validate_coordinates(
    latitude: float,
    longitude: float,
) -> None:
    if not _is_number(latitude):
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail="Latitude must be a number.",
        )

    if not _is_number(longitude):
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail="Longitude must be a number.",
        )

    if not -90 <= latitude <= 90:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail="Latitude must be between -90 and 90.",
        )

    if not -180 <= longitude <= 180:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail="Longitude must be between -180 and 180.",
        )


def _normalize_category_ids(
    category_ids: list[str] | None,
) -> list[str]:
    """Validate and remove duplicate Foursquare category IDs."""

    if category_ids is None:
        return []

    normalized_category_ids: list[str] = []

    for raw_category_id in category_ids:
        category_id = str(
            raw_category_id,
        ).strip()

        if (
            not category_id
            or len(category_id) > MAXIMUM_CATEGORY_ID_LENGTH
            or CATEGORY_ID_PATTERN.fullmatch(
                category_id,
            )
            is None
        ):
            raise HTTPException(
                status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
                detail=(
                    "Every place category ID must contain " "letters or numbers only."
                ),
            )

        if category_id not in normalized_category_ids:
            normalized_category_ids.append(
                category_id,
            )

    return normalized_category_ids


def _create_headers() -> dict[str, str]:
    settings = get_settings()

    api_key = settings.foursquare_api_key.get_secret_value().strip()

    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-Places-Api-Version": (FOURSQUARE_API_VERSION),
    }


def create_search_client() -> httpx.AsyncClient:
    """Create one task-scoped client that may serve several place searches."""

    return httpx.AsyncClient(
        timeout=httpx.Timeout(
            timeout=15.0,
            connect=5.0,
        ),
        follow_redirects=True,
    )


def _extract_error_message(
    response: httpx.Response,
) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None

    if not isinstance(payload, dict):
        return None

    for field in [
        "message",
        "detail",
        "error",
    ]:
        value = payload.get(field)

        if isinstance(value, str):
            normalized_value = value.strip()

            if normalized_value:
                return normalized_value

        if isinstance(value, dict):
            nested_message = value.get("message")

            if isinstance(
                nested_message,
                str,
            ):
                normalized_message = nested_message.strip()

                if normalized_message:
                    return normalized_message

    return None


def _provider_error_text(
    response: httpx.Response,
) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""

    text_values: list[str] = []

    def collect_text(
        value: Any,
        *,
        depth: int,
    ) -> None:
        if depth > 4 or len(text_values) >= 50:
            return

        if isinstance(value, str):
            normalized_value = " ".join(value.split())

            if normalized_value:
                text_values.append(normalized_value)

            return

        if isinstance(value, dict):
            for key, nested_value in value.items():
                collect_text(key, depth=depth + 1)
                collect_text(nested_value, depth=depth + 1)

            return

        if isinstance(value, list):
            for nested_value in value:
                collect_text(nested_value, depth=depth + 1)

    collect_text(payload, depth=0)

    return " ".join(text_values).casefold()


def _is_explicit_premium_metadata_access_error(
    response: httpx.Response,
) -> bool:
    if response.status_code not in {
        400,
        403,
        429,
        422,
    }:
        return False

    error_text = _provider_error_text(response)

    if not error_text:
        return False

    mentions_premium = re.search(r"\bpremium\b", error_text) is not None
    mentions_approved_field = any(
        re.search(
            rf"\b{re.escape(field_name)}\b",
            error_text,
        )
        is not None
        for field_name in APPROVED_PREMIUM_SEARCH_FIELDS
    )
    mentions_access_limitation = any(
        phrase in error_text
        for phrase in (
            "access",
            "entitle",
            "not allowed",
            "not available",
            "not enabled",
            "not permitted",
            "permission",
            "plan",
            "subscription",
            "tier",
            "upgrade",
        )
    )

    return mentions_access_limitation and (
        mentions_premium or mentions_approved_field
    )


def _retry_delay_seconds(
    response: httpx.Response,
    *,
    retry_index: int,
) -> float:
    if response.status_code == 429:
        raw_retry_after = response.headers.get("Retry-After")

        if raw_retry_after is not None:
            try:
                retry_after_seconds = int(raw_retry_after.strip())
            except ValueError:
                retry_after_seconds = -1

            if retry_after_seconds >= 0:
                return min(
                    float(retry_after_seconds),
                    MAXIMUM_RETRY_AFTER_SECONDS,
                )

    return RETRY_BACKOFF_SECONDS[retry_index]


async def _request_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    detect_premium_metadata_access_error: bool = False,
    verify_ambiguous_premium_rate_limit: bool = False,
) -> Any:
    headers = _create_headers()

    for attempt_index in range(MAXIMUM_REQUEST_ATTEMPTS):
        try:
            response = await client.get(
                url,
                params=params,
                headers=headers,
            )

        except httpx.TimeoutException as error:
            if attempt_index < MAXIMUM_REQUEST_ATTEMPTS - 1:
                await asyncio.sleep(
                    RETRY_BACKOFF_SECONDS[attempt_index],
                )
                continue

            raise HTTPException(
                status_code=(status.HTTP_504_GATEWAY_TIMEOUT),
                detail=("The place service took too long " "to respond."),
            ) from error

        except httpx.RequestError as error:
            if attempt_index < MAXIMUM_REQUEST_ATTEMPTS - 1:
                await asyncio.sleep(
                    RETRY_BACKOFF_SECONDS[attempt_index],
                )
                continue

            raise HTTPException(
                status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
                detail=("The place service is currently " "unavailable."),
            ) from error

        if (
            detect_premium_metadata_access_error
            and _is_explicit_premium_metadata_access_error(response)
        ):
            raise _PremiumMetadataAccessError

        if (
            verify_ambiguous_premium_rate_limit
            and attempt_index == 0
            and response.status_code == 429
        ):
            raise _AmbiguousPremiumMetadataRateLimitError

        if (
            response.status_code in RETRYABLE_STATUS_CODES
            and attempt_index < MAXIMUM_REQUEST_ATTEMPTS - 1
        ):
            await asyncio.sleep(
                _retry_delay_seconds(
                    response,
                    retry_index=attempt_index,
                )
            )
            continue

        break

    if response.status_code == 401:
        raise HTTPException(
            status_code=(status.HTTP_502_BAD_GATEWAY),
            detail=("The place service rejected the " "configured API key."),
        )

    if response.status_code == 429:
        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail=("The place service request limit " "has been reached."),
        )

    if response.status_code < 200 or response.status_code >= 300:
        provider_message = _extract_error_message(
            response,
        )

        raise HTTPException(
            status_code=(status.HTTP_502_BAD_GATEWAY),
            detail=(provider_message or "The place service returned an error."),
        )

    try:
        return response.json()
    except ValueError as error:
        raise HTTPException(
            status_code=(status.HTTP_502_BAD_GATEWAY),
            detail=("The place service returned " "invalid data."),
        ) from error


async def _request_search_payload_with_fields(
    client: httpx.AsyncClient,
    params: dict[str, Any],
    *,
    include_premium_metadata: bool,
    verify_ambiguous_premium_rate_limit: bool = False,
) -> Any:
    request_params = dict(params)
    request_params["fields"] = (
        SEARCH_FIELDS if include_premium_metadata else BASE_SEARCH_FIELDS
    )

    return await _request_json(
        client,
        FOURSQUARE_SEARCH_URL,
        params=request_params,
        detect_premium_metadata_access_error=include_premium_metadata,
        verify_ambiguous_premium_rate_limit=(
            include_premium_metadata
            and verify_ambiguous_premium_rate_limit
        ),
    )


async def _request_search_payload_with_premium_fallback(
    client: httpx.AsyncClient,
    params: dict[str, Any],
    *,
    verify_ambiguous_premium_rate_limit: bool = False,
) -> Any:
    try:
        payload = await _request_search_payload_with_fields(
            client,
            params,
            include_premium_metadata=True,
            verify_ambiguous_premium_rate_limit=(
                verify_ambiguous_premium_rate_limit
            ),
        )
    except (
        _PremiumMetadataAccessError,
        _AmbiguousPremiumMetadataRateLimitError,
    ):
        payload = await _request_search_payload_with_fields(
            client,
            params,
            include_premium_metadata=False,
        )
        _mark_premium_metadata_capability(
            _PREMIUM_CAPABILITY_UNAVAILABLE,
        )
        return payload

    _mark_premium_metadata_capability(
        _PREMIUM_CAPABILITY_AVAILABLE,
    )
    return payload


async def _request_search_payload(
    client: httpx.AsyncClient,
    params: dict[str, Any],
) -> Any:
    capability = _current_premium_metadata_capability()

    if capability == _PREMIUM_CAPABILITY_AVAILABLE:
        return await _request_search_payload_with_premium_fallback(
            client,
            params,
        )

    if capability == _PREMIUM_CAPABILITY_UNAVAILABLE:
        return await _request_search_payload_with_fields(
            client,
            params,
            include_premium_metadata=False,
        )

    async with _premium_metadata_capability_lock:
        capability = _current_premium_metadata_capability()

        if capability == _PREMIUM_CAPABILITY_UNAVAILABLE:
            return await _request_search_payload_with_fields(
                client,
                params,
                include_premium_metadata=False,
            )

        if capability == _PREMIUM_CAPABILITY_AVAILABLE:
            return await _request_search_payload_with_premium_fallback(
                client,
                params,
            )

        return await _request_search_payload_with_premium_fallback(
            client,
            params,
            verify_ambiguous_premium_rate_limit=True,
        )


def _normalize_categories(
    raw_categories: Any,
) -> list[dict[str, Any]]:
    if not isinstance(
        raw_categories,
        list,
    ):
        return []

    categories: list[dict[str, Any]] = []

    for raw_category in raw_categories:
        if not isinstance(
            raw_category,
            dict,
        ):
            continue

        raw_category_id = raw_category.get("fsq_category_id")

        if raw_category_id is None:
            raw_category_id = raw_category.get("id")

        category_id = str(raw_category_id or "").strip()

        category_name = str(raw_category.get("name") or "").strip()

        if not category_name:
            continue

        categories.append(
            {
                "id": category_id or None,
                "name": category_name,
            }
        )

    return categories


def _normalize_location(
    raw_location: Any,
) -> dict[str, Any]:
    if not isinstance(
        raw_location,
        dict,
    ):
        return {
            "address": None,
            "locality": None,
            "region": None,
            "country": None,
            "displayAddress": None,
        }

    address = str(raw_location.get("address") or "").strip()

    locality = str(raw_location.get("locality") or "").strip()

    region = str(raw_location.get("region") or "").strip()

    country = str(raw_location.get("country") or "").strip()

    if country.upper() == "LK":
        country = "Sri Lanka"

    raw_formatted_address = raw_location.get("formatted_address")
    formatted_address = (
        raw_formatted_address.strip()
        if isinstance(raw_formatted_address, str)
        else ""
    )

    address_parts: list[str] = []
    normalized_address_parts: set[str] = set()

    for part in (
        address,
        locality,
        country,
    ):
        if not part:
            continue

        normalized_part = _normalize_address_part(part)

        if not normalized_part or normalized_part in normalized_address_parts:
            continue

        address_parts.append(part)
        normalized_address_parts.update(
            normalized_segment
            for segment in part.split(",")
            if (normalized_segment := _normalize_address_part(segment))
        )

    display_address = formatted_address or (
        ", ".join(address_parts) if address_parts else None
    )

    return {
        "address": address or None,
        "locality": locality or None,
        "region": region or None,
        "country": country or None,
        "displayAddress": display_address,
    }


def _normalize_address_part(
    value: str,
) -> str:
    return " ".join(value.casefold().split()).strip(" ,")


def _normalize_rating(
    raw_rating: Any,
) -> float | None:
    if not _is_number(raw_rating):
        return None

    rating = float(raw_rating)

    if not math.isfinite(rating) or not 0.0 <= rating <= 10.0:
        return None

    return rating


def _normalize_hours_time(
    raw_time: Any,
    *,
    allow_next_day: bool,
    allow_24: bool,
) -> tuple[str, int, bool] | None:
    if not isinstance(raw_time, str):
        return None

    normalized_time = raw_time.strip()
    next_day = normalized_time.startswith("+")

    if next_day:
        if not allow_next_day:
            return None

        normalized_time = normalized_time[1:]

    if re.fullmatch(r"(?:\d{4}|\d{2}:\d{2})", normalized_time) is None:
        return None

    normalized_time = normalized_time.replace(":", "")

    hour = int(normalized_time[:2])
    minute = int(normalized_time[2:])

    if minute > 59:
        return None

    if hour == 24:
        if minute != 0 or not allow_24 or next_day:
            return None

    elif hour > 23:
        return None

    return (
        f"{hour:02d}:{minute:02d}",
        hour * 60 + minute,
        next_day,
    )


def _normalize_hours_interval(
    raw_interval: Any,
) -> RecommendationOpeningInterval | None:
    if not isinstance(raw_interval, dict):
        return None

    day = raw_interval.get("day")

    if isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= 7:
        return None

    opening = _normalize_hours_time(
        raw_interval.get("open"),
        allow_next_day=False,
        allow_24=False,
    )
    closing = _normalize_hours_time(
        raw_interval.get("close"),
        allow_next_day=True,
        allow_24=True,
    )

    if opening is None or closing is None:
        return None

    opening_time, opening_minutes, _ = opening
    closing_time, closing_minutes, explicit_next_day = closing
    all_day = opening_minutes == 0 and closing_minutes == 24 * 60
    overnight = explicit_next_day or (
        not all_day and closing_minutes < opening_minutes
    )

    return RecommendationOpeningInterval(
        day=day,
        openingTime=opening_time,
        closingTime=closing_time,
        overnight=overnight,
        allDay=all_day,
    )


def _normalize_hours(
    raw_hours: Any,
) -> RecommendationOpeningHours | None:
    if not isinstance(raw_hours, dict):
        return None

    raw_regular = raw_hours.get("regular")
    regular: list[RecommendationOpeningInterval] = []

    if isinstance(raw_regular, list):
        for raw_interval in raw_regular:
            interval = _normalize_hours_interval(raw_interval)

            if interval is not None:
                regular.append(interval)

    raw_open_now = raw_hours.get("open_now")
    open_now = raw_open_now if isinstance(raw_open_now, bool) else None

    raw_is_local_holiday = raw_hours.get("is_local_holiday")
    is_local_holiday = (
        raw_is_local_holiday if isinstance(raw_is_local_holiday, bool) else None
    )

    raw_display = raw_hours.get("display")
    display = raw_display.strip() if isinstance(raw_display, str) else ""

    if not regular and open_now is None and is_local_holiday is None and not display:
        return None

    return RecommendationOpeningHours(
        regular=tuple(regular),
        openNow=open_now,
        isLocalHoliday=is_local_holiday,
        display=display or None,
    )


def _is_sri_lankan_place(
    raw_location: Any,
) -> bool:
    if not isinstance(
        raw_location,
        dict,
    ):
        return True

    country = str(raw_location.get("country") or "").strip()

    if not country:
        return True

    return country.upper() in {
        "LK",
        "SRI LANKA",
    }


def _normalize_place(
    raw_place: Any,
) -> dict[str, Any] | None:
    if not isinstance(
        raw_place,
        dict,
    ):
        return None

    fsq_place_id = str(raw_place.get("fsq_place_id") or "").strip()

    name = str(raw_place.get("name") or "").strip()

    latitude = raw_place.get("latitude")

    longitude = raw_place.get("longitude")

    if not fsq_place_id or not name:
        return None

    if not _is_number(latitude):
        return None

    if not _is_number(longitude):
        return None

    if not -90 <= latitude <= 90:
        return None

    if not -180 <= longitude <= 180:
        return None

    raw_location = raw_place.get("location")

    if not _is_sri_lankan_place(
        raw_location,
    ):
        return None

    distance = raw_place.get("distance")

    if (
        not _is_number(distance)
        or not math.isfinite(float(distance))
        or float(distance) < 0
    ):
        distance = None

    telephone = str(raw_place.get("tel") or "").strip()

    website = str(raw_place.get("website") or "").strip()

    metadata = RecommendationPlaceMetadata(
        rating=_normalize_rating(
            raw_place.get("rating"),
        ),
        hours=_normalize_hours(
            raw_place.get("hours"),
        ),
    ).model_dump(
        by_alias=True,
        mode="json",
    )

    return {
        "id": fsq_place_id,
        "name": name,
        "categories": _normalize_categories(
            raw_place.get("categories"),
        ),
        "location": _normalize_location(
            raw_location,
        ),
        "latitude": float(latitude),
        "longitude": float(longitude),
        "distanceMeters": (int(distance) if distance is not None else None),
        "telephone": telephone or None,
        "website": website or None,
        **metadata,
    }


def _is_within_search_radius(
    place: dict[str, Any],
    *,
    latitude: float,
    longitude: float,
    radius: int,
) -> bool:
    place_latitude = float(place["latitude"])
    place_longitude = float(place["longitude"])

    latitude_radians = math.radians(latitude)
    place_latitude_radians = math.radians(place_latitude)
    latitude_delta = math.radians(place_latitude - latitude)
    longitude_delta = math.radians(place_longitude - longitude)

    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(latitude_radians)
        * math.cos(place_latitude_radians)
        * math.sin(longitude_delta / 2) ** 2
    )
    angular_distance = 2 * math.atan2(
        math.sqrt(haversine),
        math.sqrt(max(0.0, 1 - haversine)),
    )

    return EARTH_RADIUS_METERS * angular_distance <= radius


def _normalize_locality_text(
    value: str,
) -> str:
    normalized = unicodedata.normalize(
        "NFKC",
        value,
    ).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).strip()
    words = normalized.split()

    while words and words[-1] in {
        "city",
        "municipality",
        "town",
    }:
        words.pop()

    return " ".join(words)


def _is_one_edit_apart(
    first: str,
    second: str,
) -> bool:
    if abs(len(first) - len(second)) > 1:
        return False

    if len(first) > len(second):
        first, second = second, first

    first_index = 0
    second_index = 0
    differences = 0

    while first_index < len(first) and second_index < len(second):
        if first[first_index] == second[second_index]:
            first_index += 1
            second_index += 1
            continue

        differences += 1

        if differences > 1:
            return False

        if len(first) == len(second):
            first_index += 1

        second_index += 1

    return differences + (len(second) - second_index) <= 1


def _locality_names_match(
    expected: str,
    actual: str,
) -> bool:
    normalized_expected = _normalize_locality_text(expected).replace(" ", "")
    normalized_actual = _normalize_locality_text(actual).replace(" ", "")

    if not normalized_expected or not normalized_actual:
        return False

    if normalized_expected == normalized_actual:
        return True

    return min(len(normalized_expected), len(normalized_actual)) >= 5 and (
        _is_one_edit_apart(
            normalized_expected,
            normalized_actual,
        )
    )


def _has_conflicting_locality(
    raw_location: Any,
    *,
    expected_locality: str,
) -> bool:
    if not isinstance(raw_location, dict):
        return False

    locality_values = [
        value
        for field in (
            "locality",
            "post_town",
        )
        if isinstance((value := raw_location.get(field)), str) and value.strip()
    ]

    if not locality_values:
        return False

    if any(
        _locality_names_match(
            expected_locality,
            locality_value,
        )
        for locality_value in locality_values
    ):
        return False

    return any(
        re.search(
            r"[a-z]",
            _normalize_locality_text(locality_value),
        )
        is not None
        for locality_value in locality_values
    )


async def search_places(
    *,
    query: str | None = None,
    latitude: float,
    longitude: float,
    near: str | None = None,
    category_ids: list[str] | None = None,
    radius: int = DEFAULT_SEARCH_RADIUS_METERS,
    limit: int = 6,
    sort: str = "RELEVANCE",
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Search for Sri Lankan places with a trusted coordinate safety scope."""

    normalized_query = query.strip() if query is not None else ""
    normalized_near = near.strip() if near is not None else ""

    if normalized_near and any(ord(character) < 32 for character in normalized_near):
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail="The place search locality is invalid.",
        )

    if normalized_query and len(normalized_query) < 2:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail=("The place search query must contain " "at least two characters."),
        )

    if len(normalized_query) > 80:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail=("The place search query cannot exceed " "80 characters."),
        )

    _validate_coordinates(
        latitude,
        longitude,
    )

    normalized_category_ids = _normalize_category_ids(
        category_ids,
    )

    if not normalized_query and not normalized_category_ids:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail=(
                "A place search query or at least one category ID is required."
            ),
        )

    if radius < 1 or radius > MAXIMUM_SEARCH_RADIUS_METERS:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail=("The search radius must be between " "1 and 100000 metres."),
        )

    if limit < 1 or limit > MAXIMUM_SEARCH_RESULTS:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail=("The result limit must be between " "1 and 50."),
        )

    normalized_sort = sort.strip().upper()

    if normalized_sort not in SUPPORTED_SORT_OPTIONS:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail=("The place sort option is invalid."),
        )

    params: dict[str, Any] = {
        "limit": limit,
        "sort": normalized_sort,
    }

    if normalized_near:
        params["near"] = normalized_near
    else:
        params["ll"] = f"{latitude},{longitude}"
        params["radius"] = radius

    if normalized_query:
        params["query"] = normalized_query

    if normalized_category_ids:
        params["fsq_category_ids"] = ",".join(
            normalized_category_ids,
        )

    if client is None:
        async with create_search_client() as owned_client:
            payload = await _request_search_payload(
                owned_client,
                params,
            )
    else:
        payload = await _request_search_payload(
            client,
            params,
        )

    raw_results: Any = None

    if isinstance(payload, dict):
        raw_results = payload.get("results")

    elif isinstance(payload, list):
        raw_results = payload

    if not isinstance(
        raw_results,
        list,
    ):
        raise HTTPException(
            status_code=(status.HTTP_502_BAD_GATEWAY),
            detail=("The place service returned an " "unexpected response."),
        )

    places: list[dict[str, Any]] = []

    for raw_place in raw_results:
        place = _normalize_place(
            raw_place,
        )

        if place is not None:
            if _is_within_search_radius(
                place,
                latitude=latitude,
                longitude=longitude,
                radius=radius,
            ):
                expected_locality = normalized_near.partition(",")[0].strip()

                if not expected_locality or not _has_conflicting_locality(
                    raw_place.get("location")
                    if isinstance(raw_place, dict)
                    else None,
                    expected_locality=expected_locality,
                ):
                    places.append(place)

    return places
