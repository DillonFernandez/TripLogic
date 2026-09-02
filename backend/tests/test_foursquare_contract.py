"""Contract tests for the current Foursquare transport and normalization."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import HTTPException


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import foursquare  # noqa: E402
from app.foursquare_categories import (  # noqa: E402
    GENERIC_ATTRACTION_GROUPS,
    HOTEL_CATEGORY_ID,
)


REAL_ASYNC_CLIENT = httpx.AsyncClient


class FoursquareContractTests(unittest.IsolatedAsyncioTestCase):
    """Freeze the behavior of ``app.foursquare`` without live HTTP calls."""

    async def _search_with_provider_response(
        self,
        payload: Any,
        *,
        status_code: int = 200,
        query: str | None = "museum",
        latitude: float = 6.9271,
        longitude: float = 79.8612,
        category_ids: list[str] | None = None,
        radius: int = foursquare.DEFAULT_SEARCH_RADIUS_METERS,
        limit: int = 6,
        sort: str = "RELEVANCE",
    ) -> tuple[list[dict[str, Any]], list[httpx.Request]]:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                status_code,
                content=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                request=request,
            )

        def make_client(**kwargs: Any) -> httpx.AsyncClient:
            return REAL_ASYNC_CLIENT(
                transport=httpx.MockTransport(handler),
                **kwargs,
            )

        secret = Mock()
        secret.get_secret_value.return_value = "  contract-test-key  "
        settings = SimpleNamespace(foursquare_api_key=secret)

        with (
            patch.object(foursquare.httpx, "AsyncClient", side_effect=make_client),
            patch.object(foursquare, "get_settings", return_value=settings),
        ):
            places = await foursquare.search_places(
                query=query,
                latitude=latitude,
                longitude=longitude,
                category_ids=category_ids,
                radius=radius,
                limit=limit,
                sort=sort,
            )

        return places, requests

    async def _assert_request_error(
        self,
        *,
        status_code: int | None = None,
        payload: Any = None,
        content: bytes | None = None,
        request_exception: Exception | None = None,
        expected_status: int,
        expected_detail: str,
        expected_attempts: int = 1,
        expected_delays: tuple[float, ...] = (),
    ) -> None:
        client = Mock()

        if request_exception is not None:
            client.get = AsyncMock(side_effect=request_exception)
        else:
            response = httpx.Response(
                status_code,
                json=payload,
            ) if content is None else httpx.Response(
                status_code,
                content=content,
            )
            client.get = AsyncMock(return_value=response)

        secret = Mock()
        secret.get_secret_value.return_value = "contract-test-key"
        settings = SimpleNamespace(foursquare_api_key=secret)
        sleep = AsyncMock()

        with (
            patch.object(foursquare, "get_settings", return_value=settings),
            patch.object(foursquare.asyncio, "sleep", sleep),
        ):
            with self.assertRaises(HTTPException) as raised:
                await foursquare._request_json(
                    client,
                    foursquare.FOURSQUARE_SEARCH_URL,
                    params={"query": "museum"},
                )

        self.assertEqual(raised.exception.status_code, expected_status)
        self.assertEqual(raised.exception.detail, expected_detail)
        self.assertEqual(client.get.await_count, expected_attempts)
        self.assertEqual(
            [call.args[0] for call in sleep.await_args_list],
            list(expected_delays),
        )

    async def _request_with_outcomes(
        self,
        outcomes: list[httpx.Response | Exception],
    ) -> tuple[Any, AsyncMock, AsyncMock]:
        client = Mock()
        client.get = AsyncMock(side_effect=outcomes)

        secret = Mock()
        secret.get_secret_value.return_value = "contract-test-key"
        settings = SimpleNamespace(foursquare_api_key=secret)
        sleep = AsyncMock()

        with (
            patch.object(foursquare, "get_settings", return_value=settings),
            patch.object(foursquare.asyncio, "sleep", sleep),
        ):
            result = await foursquare._request_json(
                client,
                foursquare.FOURSQUARE_SEARCH_URL,
                params={"query": "museum"},
            )

        return result, client.get, sleep

    async def _assert_search_validation_error(
        self,
        *,
        expected_detail: str,
        **overrides: Any,
    ) -> None:
        arguments: dict[str, Any] = {
            "query": "museum",
            "latitude": 6.9271,
            "longitude": 79.8612,
        }
        arguments.update(overrides)

        with patch.object(foursquare.httpx, "AsyncClient") as client_class:
            with self.assertRaises(HTTPException) as raised:
                await foursquare.search_places(**arguments)

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(raised.exception.detail, expected_detail)
        client_class.assert_not_called()

    async def test_search_transport_endpoint_headers_and_parameters(self) -> None:
        places, requests = await self._search_with_provider_response(
            {"results": []},
            query="  art museum  ",
            latitude=7.2906,
            longitude=80.6337,
            category_ids=["10001", "ABC2", "10001"],
            radius=12_345,
            limit=17,
            sort="distance",
        )

        self.assertEqual(places, [])
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(str(request.url.copy_with(query=None)), foursquare.FOURSQUARE_SEARCH_URL)
        self.assertEqual(request.headers["Authorization"], "Bearer contract-test-key")
        self.assertEqual(request.headers["X-Places-Api-Version"], "2025-06-17")
        self.assertEqual(request.headers["Accept"], "application/json")
        self.assertEqual(request.url.params["query"], "art museum")
        self.assertEqual(request.url.params["ll"], "7.2906,80.6337")
        self.assertEqual(request.url.params["radius"], "12345")
        self.assertEqual(request.url.params["limit"], "17")
        self.assertEqual(request.url.params["sort"], "DISTANCE")
        self.assertEqual(request.url.params["fields"], foursquare.SEARCH_FIELDS)
        self.assertEqual(request.url.params["fsq_category_ids"], "10001,ABC2")

    async def test_one_category_id_produces_one_category_parameter(self) -> None:
        _, requests = await self._search_with_provider_response(
            {"results": []},
            category_ids=[HOTEL_CATEGORY_ID],
        )

        self.assertEqual(
            requests[0].url.params["fsq_category_ids"],
            HOTEL_CATEGORY_ID,
        )

    async def test_category_only_search_omits_query_parameter(self) -> None:
        _, requests = await self._search_with_provider_response(
            {"results": []},
            query=None,
            category_ids=[HOTEL_CATEGORY_ID],
        )

        self.assertNotIn("query", requests[0].url.params)
        self.assertEqual(
            requests[0].url.params["fsq_category_ids"],
            HOTEL_CATEGORY_ID,
        )

    async def test_blank_query_with_categories_is_normalized_to_omission(
        self,
    ) -> None:
        for query in ("", "   "):
            with self.subTest(query=query):
                _, requests = await self._search_with_provider_response(
                    {"results": []},
                    query=query,
                    category_ids=[HOTEL_CATEGORY_ID],
                )

                self.assertNotIn("query", requests[0].url.params)

    async def test_unconstrained_search_is_rejected_before_http(self) -> None:
        for query, category_ids in (
            (None, None),
            (None, []),
            ("", None),
            ("   ", []),
        ):
            with self.subTest(query=query, category_ids=category_ids):
                await self._assert_search_validation_error(
                    query=query,
                    category_ids=category_ids,
                    expected_detail=(
                        "A place search query or at least one category ID "
                        "is required."
                    ),
                )

    async def test_nonempty_query_without_categories_still_works(self) -> None:
        _, requests = await self._search_with_provider_response(
            {"results": []},
            query="museum",
            category_ids=None,
        )

        self.assertEqual(requests[0].url.params["query"], "museum")
        self.assertNotIn("fsq_category_ids", requests[0].url.params)

    async def test_supplied_query_length_validation_is_unchanged(self) -> None:
        for query, expected_detail in (
            (
                "x",
                "The place search query must contain at least two characters.",
            ),
            (
                "x" * 81,
                "The place search query cannot exceed 80 characters.",
            ),
        ):
            with self.subTest(query_length=len(query)):
                await self._assert_search_validation_error(
                    query=query,
                    category_ids=[HOTEL_CATEGORY_ID],
                    expected_detail=expected_detail,
                )

    async def test_duplicate_category_ids_are_deduplicated_in_order(self) -> None:
        _, requests = await self._search_with_provider_response(
            {"results": []},
            category_ids=[" first ", "second", "first"],
        )

        self.assertEqual(
            requests[0].url.params["fsq_category_ids"],
            "first,second",
        )

    async def test_eight_verified_category_ids_are_accepted(self) -> None:
        category_ids = list(
            GENERIC_ATTRACTION_GROUPS["heritage_and_culture"]
        )

        _, requests = await self._search_with_provider_response(
            {"results": []},
            category_ids=category_ids,
        )

        self.assertEqual(len(category_ids), 8)
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            requests[0].url.params["fsq_category_ids"],
            ",".join(category_ids),
        )

    async def test_category_parameter_is_omitted_for_none_or_empty_ids(self) -> None:
        for category_ids in (None, []):
            with self.subTest(category_ids=category_ids):
                _, requests = await self._search_with_provider_response(
                    {"results": []},
                    category_ids=category_ids,
                )

                self.assertNotIn("fsq_category_ids", requests[0].url.params)

    async def test_empty_results_are_returned(self) -> None:
        places, _ = await self._search_with_provider_response({"results": []})

        self.assertEqual(places, [])

    async def test_valid_place_is_normalized(self) -> None:
        payload = {
            "results": [
                {
                    "fsq_place_id": "  place-123  ",
                    "name": "  National Museum  ",
                    "categories": [
                        {"fsq_category_id": "10027", "name": "  Museum  "},
                        {"id": 16000, "name": "Landmark"},
                        {"fsq_category_id": "ignored", "name": "  "},
                        "malformed",
                    ],
                    "location": {
                        "address": "Sir Marcus Fernando Mawatha",
                        "locality": "Colombo",
                        "region": "Colombo",
                        "country": "LK",
                    },
                    "latitude": 6.9271,
                    "longitude": 79.8612,
                    "distance": 321.9,
                    "tel": "  +94 11 269 4767  ",
                    "website": "  https://example.test/museum  ",
                }
            ]
        }

        places, _ = await self._search_with_provider_response(payload)

        self.assertEqual(
            places,
            [
                {
                    "id": "place-123",
                    "name": "National Museum",
                    "categories": [
                        {"id": "10027", "name": "Museum"},
                        {"id": "16000", "name": "Landmark"},
                    ],
                    "location": {
                        "address": "Sir Marcus Fernando Mawatha",
                        "locality": "Colombo",
                        "region": "Colombo",
                        "country": "Sri Lanka",
                        "displayAddress": (
                            "Sir Marcus Fernando Mawatha, Colombo, Sri Lanka"
                        ),
                    },
                    "latitude": 6.9271,
                    "longitude": 79.8612,
                    "distanceMeters": 321,
                    "telephone": "+94 11 269 4767",
                    "website": "https://example.test/museum",
                    "rating": None,
                    "hours": None,
                }
            ],
        )

    async def test_missing_optional_place_fields_normalize_to_empty_or_null(self) -> None:
        payload = {
            "results": [
                {
                    "fsq_place_id": "place-123",
                    "name": "National Museum",
                    "latitude": 6.9271,
                    "longitude": 79.8612,
                }
            ]
        }

        places, _ = await self._search_with_provider_response(payload)

        self.assertEqual(places[0]["categories"], [])
        self.assertEqual(
            places[0]["location"],
            {
                "address": None,
                "locality": None,
                "region": None,
                "country": None,
                "displayAddress": None,
            },
        )
        self.assertIsNone(places[0]["distanceMeters"])
        self.assertIsNone(places[0]["telephone"])
        self.assertIsNone(places[0]["website"])
        self.assertIsNone(places[0]["rating"])
        self.assertIsNone(places[0]["hours"])

    async def test_places_with_missing_or_blank_provider_identity_are_discarded(self) -> None:
        payload = {
            "results": [
                {"name": "No ID", "latitude": 6.9, "longitude": 79.8},
                {
                    "fsq_place_id": "   ",
                    "name": "Blank ID",
                    "latitude": 6.9,
                    "longitude": 79.8,
                },
                {
                    "fsq_place_id": "no-name",
                    "latitude": 6.9,
                    "longitude": 79.8,
                },
                {
                    "fsq_place_id": "blank-name",
                    "name": "   ",
                    "latitude": 6.9,
                    "longitude": 79.8,
                },
                "not-a-place",
                {
                    "fsq_place_id": "valid",
                    "name": "Valid",
                    "latitude": 6.9,
                    "longitude": 79.8,
                },
            ]
        }

        places, _ = await self._search_with_provider_response(payload)

        self.assertEqual([place["id"] for place in places], ["valid"])

    async def test_places_with_missing_or_non_numeric_coordinates_are_discarded(self) -> None:
        payload = {
            "results": [
                {"fsq_place_id": "missing-lat", "name": "A", "longitude": 79.8},
                {"fsq_place_id": "missing-lon", "name": "B", "latitude": 6.9},
                {
                    "fsq_place_id": "string-lat",
                    "name": "C",
                    "latitude": "6.9",
                    "longitude": 79.8,
                },
                {
                    "fsq_place_id": "boolean-lon",
                    "name": "D",
                    "latitude": 6.9,
                    "longitude": False,
                },
                {
                    "fsq_place_id": "valid",
                    "name": "Valid",
                    "latitude": 6.9,
                    "longitude": 79.8,
                },
            ]
        }

        places, _ = await self._search_with_provider_response(payload)

        self.assertEqual([place["id"] for place in places], ["valid"])

    async def test_invalid_provider_coordinates_are_discarded(self) -> None:
        invalid_coordinates = (
            ("latitude-above-maximum", 90.0001, 79.8),
            ("latitude-below-minimum", -90.0001, 79.8),
            ("longitude-above-maximum", 6.9, 180.0001),
            ("longitude-below-minimum", 6.9, -180.0001),
            ("nan-latitude", float("nan"), 79.8),
            ("nan-longitude", 6.9, float("nan")),
            ("positive-infinite-latitude", float("inf"), 79.8),
            ("negative-infinite-latitude", float("-inf"), 79.8),
            ("positive-infinite-longitude", 6.9, float("inf")),
            ("negative-infinite-longitude", 6.9, float("-inf")),
            ("boolean-latitude", True, 79.8),
            ("boolean-longitude", 6.9, False),
        )

        for place_id, latitude, longitude in invalid_coordinates:
            with self.subTest(place_id=place_id):
                payload = {
                    "results": [
                        {
                            "fsq_place_id": place_id,
                            "name": "Invalid coordinates",
                            "latitude": latitude,
                            "longitude": longitude,
                        }
                    ]
                }

                places, _ = await self._search_with_provider_response(payload)

                self.assertEqual(places, [])

    async def test_provider_coordinate_boundary_values_are_accepted_unchanged(self) -> None:
        boundary_places = [
            {
                "fsq_place_id": "minimum-latitude",
                "name": "Minimum latitude",
                "latitude": -90,
                "longitude": 79.8,
            },
            {
                "fsq_place_id": "maximum-latitude",
                "name": "Maximum latitude",
                "latitude": 90,
                "longitude": 79.8,
            },
            {
                "fsq_place_id": "minimum-longitude",
                "name": "Minimum longitude",
                "latitude": 6.9,
                "longitude": -180,
            },
            {
                "fsq_place_id": "maximum-longitude",
                "name": "Maximum longitude",
                "latitude": 6.9,
                "longitude": 180,
            },
        ]

        places = [
            place
            for raw_place in boundary_places
            if (place := foursquare._normalize_place(raw_place)) is not None
        ]

        self.assertEqual(
            [(place["latitude"], place["longitude"]) for place in places],
            [(-90.0, 79.8), (90.0, 79.8), (6.9, -180.0), (6.9, 180.0)],
        )

    async def test_mixed_valid_and_invalid_provider_places_return_only_valid(self) -> None:
        payload = {
            "results": [
                {
                    "fsq_place_id": "invalid-latitude",
                    "name": "Invalid latitude",
                    "latitude": 91,
                    "longitude": 79.8,
                },
                {
                    "fsq_place_id": "valid-one",
                    "name": "Valid one",
                    "latitude": 6.9,
                    "longitude": 79.8,
                },
                {
                    "fsq_place_id": "invalid-longitude",
                    "name": "Invalid longitude",
                    "latitude": 6.9,
                    "longitude": float("inf"),
                },
                {
                    "fsq_place_id": "valid-two",
                    "name": "Valid two",
                    "latitude": 6.91,
                    "longitude": 79.81,
                },
            ]
        }

        places, _ = await self._search_with_provider_response(payload)

        self.assertEqual([place["id"] for place in places], ["valid-one", "valid-two"])

    async def test_places_outside_configured_geographic_scope_are_discarded(
        self,
    ) -> None:
        payload = {
            "results": [
                {
                    "fsq_place_id": "inside",
                    "name": "Inside scope without an address",
                    "latitude": 6.93,
                    "longitude": 79.86,
                },
                {
                    "fsq_place_id": "outside",
                    "name": "Outside scope",
                    "latitude": 7.2906,
                    "longitude": 80.6336,
                },
            ]
        }

        places, _ = await self._search_with_provider_response(
            payload,
            latitude=6.9271,
            longitude=79.8612,
            radius=5_000,
        )

        self.assertEqual([place["id"] for place in places], ["inside"])
        self.assertIsNone(places[0]["location"]["address"])

    async def test_duplicate_provider_places_are_currently_retained(self) -> None:
        raw_place = {
            "fsq_place_id": "duplicate",
            "name": "Same place",
            "latitude": 6.9,
            "longitude": 79.8,
        }

        places, _ = await self._search_with_provider_response(
            {"results": [raw_place, dict(raw_place)]}
        )

        self.assertEqual([place["id"] for place in places], ["duplicate", "duplicate"])

    async def test_http_401_is_mapped_to_bad_gateway(self) -> None:
        await self._assert_request_error(
            status_code=401,
            payload={"message": "unauthorized"},
            expected_status=502,
            expected_detail="The place service rejected the configured API key.",
        )

    async def test_http_429_is_mapped_to_service_unavailable(self) -> None:
        await self._assert_request_error(
            status_code=429,
            payload={"message": "rate limited"},
            expected_status=503,
            expected_detail="The place service request limit has been reached.",
            expected_attempts=3,
            expected_delays=foursquare.RETRY_BACKOFF_SECONDS,
        )

    async def test_other_provider_error_preserves_a_provider_message(self) -> None:
        await self._assert_request_error(
            status_code=500,
            payload={"error": {"message": "Provider failed"}},
            expected_status=502,
            expected_detail="Provider failed",
            expected_attempts=3,
            expected_delays=foursquare.RETRY_BACKOFF_SECONDS,
        )

    async def test_other_provider_error_without_a_message_uses_generic_detail(self) -> None:
        await self._assert_request_error(
            status_code=400,
            payload={"error": []},
            expected_status=502,
            expected_detail="The place service returned an error.",
        )

    async def test_timeout_is_mapped_to_gateway_timeout(self) -> None:
        request = httpx.Request("GET", foursquare.FOURSQUARE_SEARCH_URL)
        await self._assert_request_error(
            request_exception=httpx.ReadTimeout("timed out", request=request),
            expected_status=504,
            expected_detail="The place service took too long to respond.",
            expected_attempts=3,
            expected_delays=foursquare.RETRY_BACKOFF_SECONDS,
        )

    async def test_request_error_is_mapped_to_service_unavailable(self) -> None:
        request = httpx.Request("GET", foursquare.FOURSQUARE_SEARCH_URL)
        await self._assert_request_error(
            request_exception=httpx.ConnectError("connection failed", request=request),
            expected_status=503,
            expected_detail="The place service is currently unavailable.",
            expected_attempts=3,
            expected_delays=foursquare.RETRY_BACKOFF_SECONDS,
        )

    async def test_successful_request_performs_one_attempt(self) -> None:
        expected_payload = {"results": []}

        payload, get, sleep = await self._request_with_outcomes(
            [httpx.Response(200, json=expected_payload)]
        )

        self.assertEqual(payload, expected_payload)
        self.assertEqual(get.await_count, 1)
        sleep.assert_not_awaited()

    async def test_timeout_then_success_is_retried(self) -> None:
        request = httpx.Request("GET", foursquare.FOURSQUARE_SEARCH_URL)
        expected_payload = {"results": []}

        payload, get, sleep = await self._request_with_outcomes(
            [
                httpx.ReadTimeout("timed out", request=request),
                httpx.Response(200, json=expected_payload),
            ]
        )

        self.assertEqual(payload, expected_payload)
        self.assertEqual(get.await_count, 2)
        sleep.assert_awaited_once_with(foursquare.RETRY_BACKOFF_SECONDS[0])

    async def test_request_error_then_success_is_retried(self) -> None:
        request = httpx.Request("GET", foursquare.FOURSQUARE_SEARCH_URL)
        expected_payload = {"results": []}

        payload, get, sleep = await self._request_with_outcomes(
            [
                httpx.ConnectError("connection failed", request=request),
                httpx.Response(200, json=expected_payload),
            ]
        )

        self.assertEqual(payload, expected_payload)
        self.assertEqual(get.await_count, 2)
        sleep.assert_awaited_once_with(foursquare.RETRY_BACKOFF_SECONDS[0])

    async def test_http_429_then_success_is_retried(self) -> None:
        expected_payload = {"results": []}

        payload, get, sleep = await self._request_with_outcomes(
            [
                httpx.Response(429, json={"message": "rate limited"}),
                httpx.Response(200, json=expected_payload),
            ]
        )

        self.assertEqual(payload, expected_payload)
        self.assertEqual(get.await_count, 2)
        sleep.assert_awaited_once_with(foursquare.RETRY_BACKOFF_SECONDS[0])

    async def test_http_429_integer_retry_after_is_used(self) -> None:
        _, get, sleep = await self._request_with_outcomes(
            [
                httpx.Response(
                    429,
                    json={"message": "rate limited"},
                    headers={"Retry-After": "2"},
                ),
                httpx.Response(200, json={"results": []}),
            ]
        )

        self.assertEqual(get.await_count, 2)
        sleep.assert_awaited_once_with(2.0)

    async def test_http_429_excessive_retry_after_is_capped(self) -> None:
        _, get, sleep = await self._request_with_outcomes(
            [
                httpx.Response(
                    429,
                    json={"message": "rate limited"},
                    headers={"Retry-After": "3600"},
                ),
                httpx.Response(200, json={"results": []}),
            ]
        )

        self.assertEqual(get.await_count, 2)
        sleep.assert_awaited_once_with(foursquare.MAXIMUM_RETRY_AFTER_SECONDS)

    async def test_http_429_invalid_retry_after_uses_backoff(self) -> None:
        _, get, sleep = await self._request_with_outcomes(
            [
                httpx.Response(
                    429,
                    json={"message": "rate limited"},
                    headers={"Retry-After": "later"},
                ),
                httpx.Response(200, json={"results": []}),
            ]
        )

        self.assertEqual(get.await_count, 2)
        sleep.assert_awaited_once_with(foursquare.RETRY_BACKOFF_SECONDS[0])

    async def test_retryable_http_5xx_then_success_is_retried(self) -> None:
        for status_code in (500, 502, 503, 504):
            with self.subTest(status_code=status_code):
                payload, get, sleep = await self._request_with_outcomes(
                    [
                        httpx.Response(status_code, json={"message": "temporary"}),
                        httpx.Response(200, json={"results": []}),
                    ]
                )

                self.assertEqual(payload, {"results": []})
                self.assertEqual(get.await_count, 2)
                sleep.assert_awaited_once_with(foursquare.RETRY_BACKOFF_SECONDS[0])

    async def test_repeated_retryable_http_5xx_stops_after_three_attempts(self) -> None:
        await self._assert_request_error(
            status_code=503,
            payload={"message": "still unavailable"},
            expected_status=502,
            expected_detail="still unavailable",
            expected_attempts=3,
            expected_delays=foursquare.RETRY_BACKOFF_SECONDS,
        )

    async def test_other_non_retryable_client_errors_are_not_retried(self) -> None:
        for status_code in (403, 404, 422):
            with self.subTest(status_code=status_code):
                await self._assert_request_error(
                    status_code=status_code,
                    payload={"error": []},
                    expected_status=502,
                    expected_detail="The place service returned an error.",
                )

    async def test_malformed_success_json_is_rejected(self) -> None:
        await self._assert_request_error(
            status_code=200,
            content=b"{not-json",
            expected_status=502,
            expected_detail="The place service returned invalid data.",
        )

    async def test_unexpected_provider_envelopes_are_rejected(self) -> None:
        malformed_payloads = (
            None,
            "not-an-envelope",
            {},
            {"results": None},
            {"results": {}},
        )

        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(HTTPException) as raised:
                    await self._search_with_provider_response(payload)

                self.assertEqual(raised.exception.status_code, 502)
                self.assertEqual(
                    raised.exception.detail,
                    "The place service returned an unexpected response.",
                )

    async def test_top_level_provider_result_list_is_currently_accepted(self) -> None:
        payload = [
            {
                "fsq_place_id": "top-level",
                "name": "Top-level result",
                "latitude": 6.9,
                "longitude": 79.8,
            }
        ]

        places, _ = await self._search_with_provider_response(payload)

        self.assertEqual([place["id"] for place in places], ["top-level"])

    async def test_invalid_radius_is_rejected_before_http(self) -> None:
        for radius in (0, foursquare.MAXIMUM_SEARCH_RADIUS_METERS + 1):
            with self.subTest(radius=radius):
                await self._assert_search_validation_error(
                    radius=radius,
                    expected_detail=(
                        "The search radius must be between 1 and 100000 metres."
                    ),
                )

    async def test_invalid_limit_is_rejected_before_http(self) -> None:
        for limit in (0, foursquare.MAXIMUM_SEARCH_RESULTS + 1):
            with self.subTest(limit=limit):
                await self._assert_search_validation_error(
                    limit=limit,
                    expected_detail="The result limit must be between 1 and 50.",
                )

    async def test_invalid_sort_is_rejected_before_http(self) -> None:
        await self._assert_search_validation_error(
            sort="nearest",
            expected_detail="The place sort option is invalid.",
        )

    async def test_malformed_category_ids_are_rejected_before_http(self) -> None:
        invalid_category_lists = (
            [""],
            ["   "],
            ["food-and-drink"],
            ["x" * (foursquare.MAXIMUM_CATEGORY_ID_LENGTH + 1)],
        )

        for category_ids in invalid_category_lists:
            with self.subTest(category_ids=category_ids):
                await self._assert_search_validation_error(
                    category_ids=category_ids,
                    expected_detail=(
                        "Every place category ID must contain letters or numbers only."
                    ),
                )

    async def test_more_than_three_unique_category_ids_are_accepted(self) -> None:
        category_ids = list(
            GENERIC_ATTRACTION_GROUPS["family_and_learning"]
        )

        _, requests = await self._search_with_provider_response(
            {"results": []},
            category_ids=category_ids,
        )

        self.assertEqual(len(category_ids), 4)
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            requests[0].url.params["fsq_category_ids"],
            ",".join(category_ids),
        )


if __name__ == "__main__":
    unittest.main()
