"""Step 13 contracts for named-locality Foursquare discovery."""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import httpx


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("FOURSQUARE_API_KEY", "locality-precision-test-key")
os.environ.setdefault("OPENROUTESERVICE_API_KEY", "locality-precision-test-key")
os.environ.setdefault("OPENAI_API_KEY", "locality-precision-test-key")
os.environ.setdefault(
    "FIREBASE_CREDENTIALS_PATH",
    str(BACKEND_ROOT / "triplogic-33010-firebase-adminsdk-fbsvc-e7ac89e001.json"),
)

from app import foursquare, recommendation_engine  # noqa: E402
from app.conversation_location_verifier import (  # noqa: E402
    LocationResolutionStatus,
    resolve_location_results,
)
from app.conversation_models import (  # noqa: E402
    TravelContext,
    TravelContextStage,
    TravelLocation,
    TravelLocationSource,
    TravelRequestGroup,
    TravelRequestKind,
    TravellerType,
)
from app.conversation_recommendation_adapter import (  # noqa: E402
    build_recommendation_tasks,
)
from app.foursquare_categories import (  # noqa: E402
    GENERIC_ATTRACTION_GROUPS,
    HOTEL_CATEGORY_ID,
    INTENT_CATEGORY_PRESETS,
    RESTAURANT_CATEGORY_ID,
)


REAL_ASYNC_CLIENT = httpx.AsyncClient
SRI_LANKA_TIMEZONE = ZoneInfo("Asia/Colombo")
MISSING = object()


class FoursquareLocalityPrecisionTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _provider_place(
        place_id: str,
        name: str,
        *,
        latitude: float,
        longitude: float,
        locality: object = MISSING,
        post_town: object = MISSING,
    ) -> dict[str, Any]:
        location: dict[str, Any] = {
            "country": "LK",
            "region": "Uva Province",
        }

        if locality is not MISSING:
            location["locality"] = locality

        if post_town is not MISSING:
            location["post_town"] = post_town

        return {
            "fsq_place_id": place_id,
            "name": name,
            "categories": [
                {
                    "fsq_category_id": HOTEL_CATEGORY_ID,
                    "name": "Hotel",
                }
            ],
            "location": location,
            "latitude": latitude,
            "longitude": longitude,
            "distance": 100,
        }

    async def _search(
        self,
        results: list[dict[str, Any]],
        *,
        near: str | None,
        latitude: float = 6.76566,
        longitude: float = 80.95104,
        radius: int = 20_000,
    ) -> tuple[list[dict[str, Any]], httpx.Request]:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                content=json.dumps({"results": results}).encode("utf-8"),
                request=request,
            )

        def make_client(**kwargs: Any) -> httpx.AsyncClient:
            return REAL_ASYNC_CLIENT(
                transport=httpx.MockTransport(handler),
                **kwargs,
            )

        secret = Mock()
        secret.get_secret_value.return_value = "locality-precision-test-key"
        settings = SimpleNamespace(foursquare_api_key=secret)

        arguments: dict[str, Any] = {
            "query": "hotel",
            "latitude": latitude,
            "longitude": longitude,
            "category_ids": [HOTEL_CATEGORY_ID],
            "radius": radius,
        }

        if near is not None:
            arguments["near"] = near

        with (
            patch.object(foursquare.httpx, "AsyncClient", side_effect=make_client),
            patch.object(foursquare, "get_settings", return_value=settings),
        ):
            places = await foursquare.search_places(**arguments)

        self.assertEqual(len(requests), 1)
        return places, requests[0]

    @staticmethod
    def _location(
        name: str,
        latitude: float,
        longitude: float,
        *,
        canonical_name: str | None,
        admin1: str | None = None,
        admin2: str | None = None,
    ) -> TravelLocation:
        return TravelLocation(
            displayName=name,
            localityName=canonical_name,
            source=TravelLocationSource.SEARCHED,
            latitude=latitude,
            longitude=longitude,
            countryCode="LK",
            admin1=admin1,
            admin2=admin2,
            verified=True,
        )

    def _context(
        self,
        *,
        kind: TravelRequestKind,
        search_location: TravelLocation,
        origin: TravelLocation | None = None,
        query: str | None = None,
    ) -> TravelContext:
        tomorrow = datetime.now(SRI_LANKA_TIMEZONE).date() + timedelta(days=1)

        return TravelContext(
            stage=TravelContextStage.CONFIRMED,
            startingLocation=origin,
            tripStartDate=tomorrow,
            tripEndDate=tomorrow,
            dailyStartTime="09:00:00",
            dailyEndTime="13:00:00",
            travellerType=TravellerType.COUPLE,
            travelModes=["driving"],
            requestGroups=[
                TravelRequestGroup(
                    id=f"{kind.value}-request",
                    kind=kind,
                    query=query or ("hotel" if kind is TravelRequestKind.HOTEL else f"{kind.value}s"),
                    searchLocation=search_location,
                )
            ],
            missingFields=[],
            uncertainties=[],
            isConfirmed=True,
        )

    async def test_named_locality_uses_near_and_omits_ll_and_radius(self) -> None:
        places, request = await self._search(
            [
                self._provider_place(
                    "haputale-hotel",
                    "Olympus Plaza",
                    latitude=6.766,
                    longitude=80.952,
                    locality="Haputale",
                )
            ],
            near="Haputale, Sri Lanka",
        )

        self.assertEqual([place["id"] for place in places], ["haputale-hotel"])
        self.assertEqual(request.url.params["near"], "Haputale, Sri Lanka")
        self.assertNotIn("ll", request.url.params)
        self.assertNotIn("radius", request.url.params)
        self.assertEqual(request.url.params["fsq_category_ids"], HOTEL_CATEGORY_ID)

    async def test_explicit_neighbor_is_rejected_but_missing_locality_is_not_fabricated(
        self,
    ) -> None:
        places, _ = await self._search(
            [
                self._provider_place(
                    "local",
                    "Haputale Hotel",
                    latitude=6.766,
                    longitude=80.952,
                    locality="Haputale",
                ),
                self._provider_place(
                    "neighbor",
                    "Ella Hotel",
                    latitude=6.8756,
                    longitude=81.0463,
                    locality="Ella",
                ),
                self._provider_place(
                    "unknown-locality",
                    "Locality Unavailable",
                    latitude=6.767,
                    longitude=80.953,
                ),
            ],
            near="Haputale, Sri Lanka",
        )

        self.assertEqual(
            [place["id"] for place in places],
            ["local", "unknown-locality"],
        )
        self.assertIsNone(places[1]["location"]["locality"])

    async def test_alternate_spelling_and_uncomparable_script_are_not_false_conflicts(
        self,
    ) -> None:
        alternate, _ = await self._search(
            [
                self._provider_place(
                    "alternate",
                    "Cues-ta",
                    latitude=6.766,
                    longitude=80.952,
                    locality="Haputhale",
                )
            ],
            near="Haputale, Sri Lanka",
        )
        localized, _ = await self._search(
            [
                self._provider_place(
                    "localized",
                    "Kandy Place",
                    latitude=7.2907,
                    longitude=80.6337,
                    locality="මහනුවර",
                )
            ],
            near="Kandy, Sri Lanka",
            latitude=7.2906,
            longitude=80.6336,
        )

        self.assertEqual([place["id"] for place in alternate], ["alternate"])
        self.assertEqual([place["id"] for place in localized], ["localized"])

    async def test_trusted_coordinate_radius_still_rejects_far_near_result(self) -> None:
        places, _ = await self._search(
            [
                self._provider_place(
                    "inside",
                    "Inside",
                    latitude=6.766,
                    longitude=80.952,
                    locality="Haputale",
                ),
                self._provider_place(
                    "outside",
                    "Outside",
                    latitude=7.1,
                    longitude=81.2,
                    locality="Haputale",
                ),
            ],
            near="Haputale, Sri Lanka",
        )

        self.assertEqual([place["id"] for place in places], ["inside"])

    async def test_major_city_small_town_and_suburb_use_same_generic_contract(
        self,
    ) -> None:
        cases = (
            ("Kandy", 7.2906, 80.6336),
            ("Haputale", 6.76566, 80.95104),
            ("Dehiwala", 6.85626, 79.86159),
        )

        for locality, latitude, longitude in cases:
            with self.subTest(locality=locality):
                places, request = await self._search(
                    [
                        self._provider_place(
                            locality.casefold(),
                            f"{locality} Place",
                            latitude=latitude,
                            longitude=longitude,
                            locality=locality,
                        )
                    ],
                    near=f"{locality}, Sri Lanka",
                    latitude=latitude,
                    longitude=longitude,
                )

                self.assertEqual(len(places), 1)
                self.assertEqual(
                    request.url.params["near"],
                    f"{locality}, Sri Lanka",
                )

    async def test_legacy_coordinate_mode_remains_available_without_canonical_locality(
        self,
    ) -> None:
        _, request = await self._search([], near=None, radius=12_345)

        self.assertEqual(request.url.params["ll"], "6.76566,80.95104")
        self.assertEqual(request.url.params["radius"], "12345")
        self.assertNotIn("near", request.url.params)

    def test_verifier_preserves_provider_canonical_locality_and_admin_metadata(
        self,
    ) -> None:
        resolution = resolve_location_results(
            query="Ella",
            results=[
                {
                    "id": 12416240,
                    "name": "Ella Town",
                    "displayName": "Ella Town, Ella Division, Sri Lanka",
                    "latitude": 6.8756,
                    "longitude": 81.0463,
                    "countryCode": "LK",
                    "admin1": "Uva Province",
                    "admin2": "Badulla District",
                    "admin3": "Ella Division",
                    "admin4": "Ella",
                    "featureCode": "PPL",
                    "population": 5000,
                }
            ],
        )

        self.assertEqual(resolution.status, LocationResolutionStatus.VERIFIED)
        self.assertIsNotNone(resolution.location)
        location = resolution.location
        assert location is not None
        self.assertEqual(location.locality_name, "Ella Town")
        self.assertEqual(location.latitude, 6.8756)
        self.assertEqual(location.longitude, 81.0463)
        self.assertEqual(location.admin1, "Uva Province")
        self.assertEqual(location.admin4, "Ella")
        self.assertEqual(location.feature_code, "PPL")
        self.assertEqual(location.population, 5000)

    async def test_origin_and_search_locality_keep_separate_provider_roles(self) -> None:
        origin = self._location(
            "Colombo, Sri Lanka",
            6.93548,
            79.84868,
            canonical_name="Colombo",
        )
        search_location = self._location(
            "Galle, Sri Lanka",
            6.0461,
            80.2103,
            canonical_name="Galle",
            admin1="Southern Province",
            admin2="Galle District",
        )
        task = build_recommendation_tasks(
            self._context(
                kind=TravelRequestKind.HOTEL,
                search_location=search_location,
                origin=origin,
            )
        )[0]
        search = AsyncMock(return_value=[])

        with patch.object(recommendation_engine, "search_places", new=search):
            await recommendation_engine._collect_candidates(task.request)

        self.assertEqual(search.await_count, 1)
        self.assertEqual(search.await_args.kwargs["near"], "Galle, Sri Lanka")
        self.assertEqual(search.await_args.kwargs["latitude"], 6.0461)
        self.assertEqual(search.await_args.kwargs["longitude"], 80.2103)
        self.assertEqual(search.await_args.kwargs["radius"], 20_000)
        self.assertEqual(
            search.await_args.kwargs["category_ids"],
            [HOTEL_CATEGORY_ID],
        )
        self.assertEqual(task.request.route_origin.display_name, "Colombo, Sri Lanka")
        self.assertEqual(task.request.location.display_name, "Galle, Sri Lanka")

    async def test_generic_attractions_keep_four_groups_category_only_and_near(self) -> None:
        request = build_recommendation_tasks(
            self._context(
                kind=TravelRequestKind.ATTRACTION,
                search_location=self._location(
                    "Ella Town, Sri Lanka",
                    6.8756,
                    81.0463,
                    canonical_name="Ella Town",
                ),
                query="attractions",
            )
        )[0].request
        search = AsyncMock(return_value=[])

        with patch.object(recommendation_engine, "search_places", new=search):
            await recommendation_engine._collect_candidates(request)

        self.assertEqual(search.await_count, 4)
        self.assertEqual(
            [call.kwargs["category_ids"] for call in search.await_args_list],
            [list(group) for group in GENERIC_ATTRACTION_GROUPS.values()],
        )
        self.assertEqual(
            [len(call.kwargs["category_ids"]) for call in search.await_args_list],
            [8, 8, 8, 4],
        )
        self.assertTrue(
            all(
                call.kwargs["query"] is None
                and call.kwargs["near"] == "Ella Town, Sri Lanka"
                and call.kwargs["radius"] == 25_000
                for call in search.await_args_list
            )
        )

    async def test_specific_attraction_keeps_query_preset_and_single_group(self) -> None:
        request = build_recommendation_tasks(
            self._context(
                kind=TravelRequestKind.ATTRACTION,
                search_location=self._location(
                    "Ella Town, Sri Lanka",
                    6.8756,
                    81.0463,
                    canonical_name="Ella Town",
                ),
                query="waterfalls",
            )
        )[0].request
        search = AsyncMock(return_value=[])

        with patch.object(recommendation_engine, "search_places", new=search):
            await recommendation_engine._collect_candidates(request)

        self.assertEqual(search.await_count, 1)
        self.assertEqual(search.await_args.kwargs["query"], "waterfalls")
        self.assertEqual(
            search.await_args.kwargs["category_ids"],
            list(INTENT_CATEGORY_PRESETS["waterfalls"]),
        )
        self.assertEqual(search.await_args.kwargs["near"], "Ella Town, Sri Lanka")

    def test_step_nine_through_twelve_invariants_remain_unchanged(self) -> None:
        self.assertEqual(recommendation_engine.MAXIMUM_ROUTE_MATRIX_CANDIDATES, 19)
        self.assertEqual(recommendation_engine.DEFAULT_RECOMMENDATION_RESULTS, 6)
        self.assertEqual(
            recommendation_engine.SEARCH_RADIUS_BY_TYPE,
            {
                "attraction": 25_000,
                "hotel": 20_000,
                "restaurant": 12_000,
            },
        )
        self.assertEqual(HOTEL_CATEGORY_ID, "4bf58dd8d48988d1fa931735")
        self.assertEqual(RESTAURANT_CATEGORY_ID, "4d4b7105d754a06374d81259")
        self.assertEqual(
            [len(group) for group in GENERIC_ATTRACTION_GROUPS.values()],
            [8, 8, 8, 4],
        )
        self.assertEqual(len(INTENT_CATEGORY_PRESETS), 15)


if __name__ == "__main__":
    unittest.main()
