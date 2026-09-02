from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import get_settings

OPENROUTESERVICE_BASE_URL = "https://api.openrouteservice.org"

MAXIMUM_MATRIX_LOCATIONS = 20

TRAVEL_MODE_PROFILES = {
    "driving": "driving-car",
    "walking": "foot-walking",
    "cycling": "cycling-regular",
}


def _is_number(
    value: Any,
) -> bool:
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


def _normalize_profile(
    travel_mode: str,
) -> str:
    normalized_mode = travel_mode.strip().lower()

    profile = TRAVEL_MODE_PROFILES.get(
        normalized_mode,
    )

    if profile is None:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail=("Travel mode must be driving, walking, or cycling."),
        )

    return profile


def _extract_error_message(
    response: httpx.Response,
) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None

    if not isinstance(payload, dict):
        return None

    error = payload.get("error")

    if isinstance(error, str):
        normalized_error = error.strip()

        if normalized_error:
            return normalized_error

    if isinstance(error, dict):
        message = error.get("message")

        if isinstance(message, str):
            normalized_message = message.strip()

            if normalized_message:
                return normalized_message

    message = payload.get("message")

    if isinstance(message, str):
        normalized_message = message.strip()

        if normalized_message:
            return normalized_message

    return None


def _normalize_matrix(
    raw_matrix: Any,
    *,
    expected_size: int,
) -> list[list[float | None]]:
    if not isinstance(raw_matrix, list) or len(raw_matrix) != expected_size:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=("The route service returned an " "unexpected matrix."),
        )

    matrix: list[list[float | None]] = []

    for raw_row in raw_matrix:
        if not isinstance(raw_row, list) or len(raw_row) != expected_size:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=("The route service returned an " "unexpected matrix row."),
            )

        row: list[float | None] = []

        for raw_value in raw_row:
            if _is_number(raw_value):
                row.append(float(raw_value))
            else:
                row.append(None)

        matrix.append(row)

    return matrix


async def get_route_matrix(
    *,
    locations: list[tuple[float, float]],
    travel_mode: str,
) -> dict[str, Any]:
    """
    Calculate durations and distances between every supplied location.

    Each location tuple must contain:
    (latitude, longitude)
    """

    if len(locations) < 2:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail=("At least two route locations " "are required."),
        )

    if len(locations) > MAXIMUM_MATRIX_LOCATIONS:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail=("A maximum of twenty route locations " "can be processed."),
        )

    profile = _normalize_profile(
        travel_mode,
    )

    normalized_locations: list[dict[str, float]] = []

    request_locations: list[list[float]] = []

    for latitude, longitude in locations:
        _validate_coordinates(
            latitude,
            longitude,
        )

        normalized_locations.append(
            {
                "latitude": float(latitude),
                "longitude": float(longitude),
            }
        )

        # OpenRouteService expects longitude first.
        request_locations.append(
            [
                float(longitude),
                float(latitude),
            ]
        )

    settings = get_settings()

    api_key = settings.openrouteservice_api_key.get_secret_value().strip()

    matrix_url = f"{OPENROUTESERVICE_BASE_URL}" f"/v2/matrix/{profile}"

    request_body = {
        "locations": request_locations,
        "metrics": [
            "duration",
            "distance",
        ],
        "units": "m",
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                timeout=20.0,
                connect=5.0,
            ),
            follow_redirects=True,
        ) as client:
            response = await client.post(
                matrix_url,
                headers={
                    "Accept": "application/json",
                    "Authorization": api_key,
                    "Content-Type": "application/json",
                },
                json=request_body,
            )

    except httpx.TimeoutException as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=("The route service took too long " "to respond."),
        ) from error

    except httpx.RequestError as error:
        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail=("The route service is currently " "unavailable."),
        ) from error

    if response.status_code in {
        401,
        403,
    }:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=("The route service rejected the " "configured API key."),
        )

    if response.status_code == 429:
        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail=("The route service request limit " "has been reached."),
        )

    if response.status_code < 200 or response.status_code >= 300:
        provider_message = _extract_error_message(
            response,
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(provider_message or "The route service returned an error."),
        )

    try:
        payload = response.json()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=("The route service returned " "invalid data."),
        ) from error

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=("The route service returned an " "unexpected response."),
        )

    location_count = len(normalized_locations)

    durations = _normalize_matrix(
        payload.get("durations"),
        expected_size=location_count,
    )

    distances = _normalize_matrix(
        payload.get("distances"),
        expected_size=location_count,
    )

    return {
        "travelMode": travel_mode.strip().lower(),
        "profile": profile,
        "locations": normalized_locations,
        "durationsSeconds": durations,
        "distancesMeters": distances,
    }
