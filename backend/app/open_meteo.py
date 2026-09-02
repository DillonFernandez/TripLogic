import math
from typing import Any

import httpx
from fastapi import HTTPException, status

OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


def _is_number(value: Any) -> bool:
    """Return true for integers and floats, excluding booleans."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


async def search_sri_lankan_locations(
    query: str,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Search Open-Meteo for verified locations in Sri Lanka."""

    normalized_query = query.strip()

    if len(normalized_query) < 2:
        return []

    safe_limit = max(1, min(limit, 20))

    params = {
        "name": normalized_query,
        "count": safe_limit,
        "language": "en",
        "format": "json",
        "countryCode": "LK",
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                timeout=10.0,
                connect=5.0,
            ),
            follow_redirects=True,
        ) as client:
            response = await client.get(
                OPEN_METEO_GEOCODING_URL,
                params=params,
            )

            response.raise_for_status()

    except httpx.TimeoutException as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The location service took too long to respond.",
        ) from error

    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The location service returned an error.",
        ) from error

    except httpx.RequestError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The location service is currently unavailable.",
        ) from error

    try:
        payload = response.json()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The location service returned an invalid response.",
        ) from error

    if not isinstance(payload, dict):
        return []

    results = payload.get("results", [])

    if not isinstance(results, list):
        return []

    locations: list[dict[str, Any]] = []

    for result in results:
        if not isinstance(result, dict):
            continue

        if str(result.get("country_code") or "").upper() != "LK":
            continue

        latitude = result.get("latitude")
        longitude = result.get("longitude")

        if (
            not _is_number(latitude)
            or not _is_number(longitude)
            or not math.isfinite(float(latitude))
            or not math.isfinite(float(longitude))
            or not -90 <= float(latitude) <= 90
            or not -180 <= float(longitude) <= 180
        ):
            continue

        name = str(result.get("name") or "").strip()
        admin1 = str(result.get("admin1") or "").strip()
        admin2 = str(result.get("admin2") or "").strip()
        admin3 = str(result.get("admin3") or "").strip()
        admin4 = str(result.get("admin4") or "").strip()
        feature_code = str(result.get("feature_code") or "").strip()
        population = result.get("population")

        if not name:
            continue

        label_parts = list(
            dict.fromkeys(
                part
                for part in [
                    name,
                    admin4,
                    admin3,
                    admin2,
                    admin1,
                ]
                if part
            )
        )

        locations.append(
            {
                "id": result.get("id"),
                "name": name,
                "displayName": ", ".join(label_parts),
                "admin1": admin1 or None,
                "admin2": admin2 or None,
                "admin3": admin3 or None,
                "admin4": admin4 or None,
                "featureCode": feature_code or None,
                "population": (
                    int(population)
                    if isinstance(population, int)
                    and not isinstance(population, bool)
                    and population >= 0
                    else None
                ),
                "latitude": float(latitude),
                "longitude": float(longitude),
                "timezone": result.get("timezone"),
                "country": str(result.get("country") or "Sri Lanka"),
                "countryCode": "LK",
            }
        )

    return locations
