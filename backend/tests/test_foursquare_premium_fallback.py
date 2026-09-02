"""Step 15 continuation contracts for optional Premium metadata capability."""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
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
    RESTAURANT_CATEGORY_ID,
)


REAL_ASYNC_CLIENT = httpx.AsyncClient
Handler = Callable[[httpx.Request], httpx.Response]


class FoursquarePremiumFallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        foursquare._reset_premium_metadata_capability()

    def tearDown(self) -> None:
        foursquare._reset_premium_metadata_capability()

    def _place(
        self,
        *,
        include_premium: bool,
    ) -> dict[str, Any]:
        place: dict[str, Any] = {
            "fsq_place_id": "provider-place",
            "name": "Provider Place",
            "categories": [
                {
                    "fsq_category_id": RESTAURANT_CATEGORY_ID,
                    "name": "Restaurant",
                }
            ],
            "location": {"locality": "Kandy", "country": "LK"},
            "latitude": 7.291,
            "longitude": 80.634,
            "distance": 75,
        }

        if include_premium:
            place["rating"] = 8.9
            place["hours"] = {
                "regular": [
                    {"day": 1, "open": "0900", "close": "1700"}
                ],
                "open_now": True,
            }

        return place

    def _success(
        self,
        request: httpx.Request,
        *,
        include_premium: bool,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": [self._place(include_premium=include_premium)]},
            request=request,
        )

    def _entitlement_error(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "error": {
                    "code": "premium_access_required",
                    "message": (
                        "The rating and hours fields are not available "
                        "on this plan."
                    ),
                }
            },
            request=request,
        )

    async def _search(
        self,
        handler: Handler,
        *,
        category_ids: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], list[httpx.Request]]:
        requests: list[httpx.Request] = []

        def captured_handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return handler(request)

        def make_client(**kwargs: Any) -> httpx.AsyncClient:
            return REAL_ASYNC_CLIENT(
                transport=httpx.MockTransport(captured_handler),
                **kwargs,
            )

        secret = Mock()
        secret.get_secret_value.return_value = "premium-fallback-test-key"
        settings = SimpleNamespace(foursquare_api_key=secret)

        with (
            patch.object(foursquare.httpx, "AsyncClient", side_effect=make_client),
            patch.object(foursquare, "get_settings", return_value=settings),
            patch.object(foursquare.asyncio, "sleep", new=AsyncMock()),
        ):
            places = await foursquare.search_places(
                query=None,
                latitude=7.2906,
                longitude=80.6337,
                near="Kandy, Sri Lanka",
                category_ids=category_ids or [RESTAURANT_CATEGORY_ID],
                radius=12_000,
            )

        return places, requests

    async def test_premium_capable_search_returns_rating_and_hours(self) -> None:
        places, requests = await self._search(
            lambda request: self._success(request, include_premium=True)
        )

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].url.params["fields"], foursquare.SEARCH_FIELDS)
        self.assertEqual(places[0]["rating"], 8.9)
        self.assertEqual(places[0]["hours"]["regular"][0]["day"], 1)
        self.assertEqual(
            foursquare._current_premium_metadata_capability(),
            foursquare._PREMIUM_CAPABILITY_AVAILABLE,
        )

    async def test_success_with_omitted_premium_fields_does_not_retry(self) -> None:
        places, requests = await self._search(
            lambda request: self._success(request, include_premium=False)
        )

        self.assertEqual(len(requests), 1)
        self.assertEqual(places[0]["rating"], None)
        self.assertEqual(places[0]["hours"], None)
        self.assertNotEqual(places[0]["rating"], 0)

    async def test_explicit_entitlement_error_falls_back_to_base_fields_once(
        self,
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.params["fields"] == foursquare.SEARCH_FIELDS:
                return self._entitlement_error(request)

            return self._success(request, include_premium=False)

        places, requests = await self._search(handler)

        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].url.params["fields"], foursquare.SEARCH_FIELDS)
        self.assertEqual(
            requests[1].url.params["fields"],
            foursquare.BASE_SEARCH_FIELDS,
        )
        self.assertEqual(
            {str(request.url.copy_with(query=None)) for request in requests},
            {foursquare.FOURSQUARE_SEARCH_URL},
        )
        self.assertEqual(places[0]["rating"], None)
        self.assertEqual(places[0]["hours"], None)
        self.assertEqual(
            foursquare._current_premium_metadata_capability(),
            foursquare._PREMIUM_CAPABILITY_UNAVAILABLE,
        )

    async def test_unavailable_capability_is_cached_for_repeated_searches(
        self,
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.params["fields"] == foursquare.SEARCH_FIELDS:
                return self._entitlement_error(request)

            return self._success(request, include_premium=False)

        _, first_requests = await self._search(handler)
        _, second_requests = await self._search(handler)

        self.assertEqual(len(first_requests), 2)
        self.assertEqual(len(second_requests), 1)
        self.assertEqual(
            second_requests[0].url.params["fields"],
            foursquare.BASE_SEARCH_FIELDS,
        )

    async def test_ttl_expiry_reprobes_and_future_upgrade_populates_metadata(
        self,
    ) -> None:
        premium_allowed = False

        def handler(request: httpx.Request) -> httpx.Response:
            is_premium = request.url.params["fields"] == foursquare.SEARCH_FIELDS

            if is_premium and not premium_allowed:
                return self._entitlement_error(request)

            return self._success(
                request,
                include_premium=is_premium and premium_allowed,
            )

        with patch.object(foursquare.time, "monotonic", return_value=1_000.0):
            _, initial_requests = await self._search(handler)

        with patch.object(
            foursquare.time,
            "monotonic",
            return_value=(
                1_000.0 + foursquare.PREMIUM_METADATA_CAPABILITY_TTL_SECONDS - 1
            ),
        ):
            _, cached_requests = await self._search(handler)

        premium_allowed = True

        with patch.object(
            foursquare.time,
            "monotonic",
            return_value=(
                1_000.0 + foursquare.PREMIUM_METADATA_CAPABILITY_TTL_SECONDS + 1
            ),
        ):
            upgraded_places, upgraded_requests = await self._search(handler)

        self.assertEqual(len(initial_requests), 2)
        self.assertEqual(len(cached_requests), 1)
        self.assertEqual(
            cached_requests[0].url.params["fields"],
            foursquare.BASE_SEARCH_FIELDS,
        )
        self.assertEqual(len(upgraded_requests), 1)
        self.assertEqual(
            upgraded_requests[0].url.params["fields"],
            foursquare.SEARCH_FIELDS,
        )
        self.assertEqual(upgraded_places[0]["rating"], 8.9)
        self.assertIsNotNone(upgraded_places[0]["hours"])

    async def test_invalid_api_key_never_triggers_premium_fallback(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                json={"message": "Invalid API key."},
                request=request,
            )

        with self.assertRaises(HTTPException) as raised:
            await self._search(handler)

        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(
            foursquare._current_premium_metadata_capability(),
            foursquare._PREMIUM_CAPABILITY_UNKNOWN,
        )

    async def test_premium_and_base_rate_limits_preserve_rate_limit_error(
        self,
    ) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                429,
                json={"message": "Request quota exceeded."},
                request=request,
            )

        with self.assertRaises(HTTPException) as raised:
            await self._search(handler)

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(len(requests), 4)
        self.assertEqual(
            requests[0].url.params["fields"],
            foursquare.SEARCH_FIELDS,
        )
        self.assertTrue(
            all(
                request.url.params["fields"] == foursquare.BASE_SEARCH_FIELDS
                for request in requests[1:]
            )
        )
        self.assertEqual(
            foursquare._current_premium_metadata_capability(),
            foursquare._PREMIUM_CAPABILITY_UNKNOWN,
        )

    async def test_ambiguous_premium_429_uses_one_successful_base_fallback(
        self,
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.params["fields"] == foursquare.SEARCH_FIELDS:
                return httpx.Response(
                    429,
                    json={"message": "Request quota exceeded."},
                    request=request,
                )

            return self._success(request, include_premium=False)

        places, first_requests = await self._search(handler)
        _, cached_requests = await self._search(handler)

        self.assertEqual(len(first_requests), 2)
        self.assertEqual(
            [request.url.params["fields"] for request in first_requests],
            [foursquare.SEARCH_FIELDS, foursquare.BASE_SEARCH_FIELDS],
        )
        self.assertIsNone(places[0]["rating"])
        self.assertIsNone(places[0]["hours"])
        self.assertEqual(len(cached_requests), 1)
        self.assertEqual(
            cached_requests[0].url.params["fields"],
            foursquare.BASE_SEARCH_FIELDS,
        )
        self.assertEqual(
            foursquare._current_premium_metadata_capability(),
            foursquare._PREMIUM_CAPABILITY_UNAVAILABLE,
        )

    async def test_ambiguous_429_ttl_expiry_allows_future_premium_success(
        self,
    ) -> None:
        premium_allowed = False

        def handler(request: httpx.Request) -> httpx.Response:
            is_premium = request.url.params["fields"] == foursquare.SEARCH_FIELDS

            if is_premium and not premium_allowed:
                return httpx.Response(
                    429,
                    json={"message": "Request quota exceeded."},
                    request=request,
                )

            return self._success(
                request,
                include_premium=is_premium and premium_allowed,
            )

        with patch.object(foursquare.time, "monotonic", return_value=2_000.0):
            _, initial_requests = await self._search(handler)

        premium_allowed = True

        with patch.object(
            foursquare.time,
            "monotonic",
            return_value=(
                2_000.0 + foursquare.PREMIUM_METADATA_CAPABILITY_TTL_SECONDS + 1
            ),
        ):
            places, upgraded_requests = await self._search(handler)

        self.assertEqual(len(initial_requests), 2)
        self.assertEqual(len(upgraded_requests), 1)
        self.assertEqual(
            upgraded_requests[0].url.params["fields"],
            foursquare.SEARCH_FIELDS,
        )
        self.assertEqual(places[0]["rating"], 8.9)
        self.assertIsNotNone(places[0]["hours"])
        self.assertEqual(
            foursquare._current_premium_metadata_capability(),
            foursquare._PREMIUM_CAPABILITY_AVAILABLE,
        )

    async def test_failed_base_verification_does_not_cache_unavailable(
        self,
    ) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)

            if request.url.params["fields"] == foursquare.SEARCH_FIELDS:
                return httpx.Response(429, request=request)

            raise httpx.ReadTimeout(
                "base verification timed out",
                request=request,
            )

        with self.assertRaises(HTTPException) as raised:
            await self._search(handler)

        self.assertEqual(raised.exception.status_code, 504)
        self.assertEqual(len(requests), 4)
        self.assertEqual(
            foursquare._current_premium_metadata_capability(),
            foursquare._PREMIUM_CAPABILITY_UNKNOWN,
        )

    async def test_explicit_premium_429_falls_back_without_premium_retry(
        self,
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.params["fields"] == foursquare.SEARCH_FIELDS:
                return httpx.Response(
                    429,
                    json={
                        "error": {
                            "code": "premium_access_required",
                            "message": (
                                "Rating and hours are not available on this plan."
                            ),
                        }
                    },
                    request=request,
                )

            return self._success(request, include_premium=False)

        places, requests = await self._search(handler)

        self.assertEqual(len(requests), 2)
        self.assertIsNone(places[0]["rating"])
        self.assertIsNone(places[0]["hours"])
        self.assertEqual(
            foursquare._current_premium_metadata_capability(),
            foursquare._PREMIUM_CAPABILITY_UNAVAILABLE,
        )

    async def test_concurrent_ambiguous_429_searches_share_one_probe(
        self,
    ) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)

            if request.url.params["fields"] == foursquare.SEARCH_FIELDS:
                return httpx.Response(429, request=request)

            return self._success(request, include_premium=False)

        def make_client(**kwargs: Any) -> httpx.AsyncClient:
            return REAL_ASYNC_CLIENT(
                transport=httpx.MockTransport(handler),
                **kwargs,
            )

        secret = Mock()
        secret.get_secret_value.return_value = "premium-fallback-test-key"
        settings = SimpleNamespace(foursquare_api_key=secret)

        with (
            patch.object(foursquare.httpx, "AsyncClient", side_effect=make_client),
            patch.object(foursquare, "get_settings", return_value=settings),
        ):
            results = await asyncio.gather(
                *(
                    foursquare.search_places(
                        latitude=7.2906,
                        longitude=80.6337,
                        near="Kandy, Sri Lanka",
                        category_ids=list(category_ids),
                        radius=25_000,
                    )
                    for category_ids in GENERIC_ATTRACTION_GROUPS.values()
                )
            )

        premium_requests = [
            request
            for request in requests
            if request.url.params["fields"] == foursquare.SEARCH_FIELDS
        ]
        base_requests = [
            request
            for request in requests
            if request.url.params["fields"] == foursquare.BASE_SEARCH_FIELDS
        ]
        self.assertEqual(len(results), 4)
        self.assertEqual(len(premium_requests), 1)
        self.assertEqual(len(base_requests), 4)

    async def test_transient_server_errors_keep_existing_retry_behavior(
        self,
    ) -> None:
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1

            if attempts < 3:
                return httpx.Response(503, request=request)

            return self._success(request, include_premium=True)

        places, requests = await self._search(handler)

        self.assertEqual(len(requests), 3)
        self.assertEqual(places[0]["rating"], 8.9)
        self.assertTrue(
            all(
                request.url.params["fields"] == foursquare.SEARCH_FIELDS
                for request in requests
            )
        )

    async def test_unrelated_malformed_request_is_not_premium_fallback(
        self,
    ) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                400,
                json={"message": "The radius parameter is malformed."},
                request=request,
            )

        with self.assertRaises(HTTPException) as raised:
            await self._search(handler)

        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            foursquare._current_premium_metadata_capability(),
            foursquare._PREMIUM_CAPABILITY_UNKNOWN,
        )

    async def test_concurrent_unknown_searches_share_one_failed_probe(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)

            if request.url.params["fields"] == foursquare.SEARCH_FIELDS:
                return self._entitlement_error(request)

            return self._success(request, include_premium=False)

        def make_client(**kwargs: Any) -> httpx.AsyncClient:
            return REAL_ASYNC_CLIENT(
                transport=httpx.MockTransport(handler),
                **kwargs,
            )

        secret = Mock()
        secret.get_secret_value.return_value = "premium-fallback-test-key"
        settings = SimpleNamespace(foursquare_api_key=secret)
        generic_groups = list(GENERIC_ATTRACTION_GROUPS.values())

        with (
            patch.object(foursquare.httpx, "AsyncClient", side_effect=make_client),
            patch.object(foursquare, "get_settings", return_value=settings),
        ):
            results = await asyncio.gather(
                *(
                    foursquare.search_places(
                        query=None,
                        latitude=7.2906,
                        longitude=80.6337,
                        near="Kandy, Sri Lanka",
                        category_ids=list(category_ids),
                        radius=25_000,
                    )
                    for category_ids in generic_groups
                )
            )

        premium_requests = [
            request
            for request in requests
            if request.url.params["fields"] == foursquare.SEARCH_FIELDS
        ]
        base_requests = [
            request
            for request in requests
            if request.url.params["fields"] == foursquare.BASE_SEARCH_FIELDS
        ]
        self.assertEqual(len(results), 4)
        self.assertEqual(len(premium_requests), 1)
        self.assertEqual(len(base_requests), 4)

    def test_only_explicitly_approved_premium_fields_are_requested(self) -> None:
        self.assertEqual(
            foursquare.APPROVED_PREMIUM_SEARCH_FIELDS,
            ("rating", "hours"),
        )
        self.assertNotIn("description", foursquare.SEARCH_FIELDS.split(","))
        self.assertNotIn("tel", foursquare.SEARCH_FIELDS.split(","))
        self.assertNotIn("website", foursquare.SEARCH_FIELDS.split(","))
        self.assertEqual(
            set(foursquare.SEARCH_FIELDS.split(","))
            - set(foursquare.BASE_SEARCH_FIELDS.split(",")),
            {"rating", "hours"},
        )
        self.assertNotIn("/details", foursquare.FOURSQUARE_SEARCH_URL)

    def test_base_fields_are_only_existing_discovery_fields(self) -> None:
        self.assertEqual(
            foursquare.BASE_SEARCH_FIELDS.split(","),
            [
                "fsq_place_id",
                "name",
                "categories",
                "location",
                "latitude",
                "longitude",
                "distance",
            ],
        )
        self.assertEqual(HOTEL_CATEGORY_ID, "4bf58dd8d48988d1fa931735")
        self.assertEqual(RESTAURANT_CATEGORY_ID, "4d4b7105d754a06374d81259")


if __name__ == "__main__":
    unittest.main()
