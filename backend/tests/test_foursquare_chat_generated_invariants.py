"""Fixed-seed generated state invariants for final chat hardening."""

from __future__ import annotations

import json
import random
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import conversation_recommendation_runner  # noqa: E402
from app.conversation_confirmation_builder import (  # noqa: E402
    build_confirmation_summary,
)
from app.conversation_confirmation_handler import (  # noqa: E402
    confirm_travel_context,
)
from app.conversation_context_patcher import (  # noqa: E402
    apply_conversation_interpretation,
)
from app.conversation_context_requirements import (  # noqa: E402
    refresh_missing_fields,
)
from app.conversation_extraction_models import (  # noqa: E402
    ConversationInterpretation,
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
    ConversationRecommendationAdapterError,
)
from app.conversation_router import _is_simple_confirmation  # noqa: E402
from app.foursquare_categories import (  # noqa: E402
    HOTEL_CATEGORY_ID,
    RESTAURANT_CATEGORY_ID,
)


GENERATED_VALID_CASES = 10_000
GENERATED_UNKNOWN_LOCATION_CASES = 100
FIXED_SEED = 2_026_09_01
SRI_LANKA_TIMEZONE = ZoneInfo("Asia/Colombo")

LOCALITIES: tuple[tuple[str, float, float], ...] = (
    ("Kandy", 7.2906, 80.6337),
    ("Galle", 6.0329, 80.2168),
    ("Ella", 6.8667, 81.0466),
    ("Negombo", 7.2083, 79.8358),
    ("Sigiriya", 7.9570, 80.7603),
    ("Haputale", 6.7667, 80.9597),
    ("Dehiwala", 6.8519, 79.8653),
    ("යාපනය", 9.6615, 80.0255),
)

QUERIES: dict[TravelRequestKind, tuple[str, ...]] = {
    TravelRequestKind.ATTRACTION: (
        "attractions",
        "Attractions",
        "scenic places",
        "historic places",
    ),
    TravelRequestKind.RESTAURANT: (
        "restaurants",
        "Restaurants",
        "places to eat",
        "Sri Lankan food",
    ),
    TravelRequestKind.HOTEL: (
        "hotels",
        "Hotels",
        "boutique hotels",
        "places to stay",
    ),
}

CONFIRMATIONS = (
    "yes",
    " okay ",
    "OK!",
    "go ahead",
    "looks good",
    "sounds good",
    "proceed please",
)


def _verified_location(name: str) -> TravelLocation:
    locality = next(item for item in LOCALITIES if item[0] == name)
    return TravelLocation(
        displayName=locality[0],
        localityName=locality[0],
        source=TravelLocationSource.SEARCHED,
        latitude=locality[1],
        longitude=locality[2],
        providerPlaceId=f"open-meteo-{abs(hash(locality[0]))}",
        countryCode="LK",
        verified=True,
    )


def _group_key(group: TravelRequestGroup) -> tuple[TravelRequestKind, str]:
    assert group.search_location is not None
    return group.kind, group.search_location.display_name


def _verify_group_locations(context: TravelContext) -> TravelContext:
    data = context.model_dump(mode="python")
    data["request_groups"] = [
        group.model_copy(
            update={
                "search_location": _verified_location(
                    group.search_location.display_name
                )
            }
        ).model_dump(mode="python")
        for group in context.request_groups
    ]
    return refresh_missing_fields(TravelContext.model_validate(data))


def _awaiting_context(context: TravelContext) -> TravelContext:
    refreshed = refresh_missing_fields(context)
    if not refreshed.is_ready_for_confirmation:
        raise AssertionError(
            "generated context is not ready: "
            f"missing={refreshed.missing_fields!r}, "
            f"uncertainties={refreshed.uncertainties!r}, "
            f"groups={[(group.kind.value, group.search_location) for group in refreshed.request_groups]!r}"
        )
    summary = build_confirmation_summary(refreshed)
    data = refreshed.model_dump(mode="python")
    data["stage"] = TravelContextStage.AWAITING_CONFIRMATION
    data["is_confirmed"] = False
    data["confirmation_summary"] = summary
    return TravelContext.model_validate(data)


class GeneratedFoursquareChatInvariantTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_ten_thousand_generated_valid_chat_states(self) -> None:
        rng = random.Random(FIXED_SEED)
        kinds = tuple(TravelRequestKind)
        available_pairs = [
            (kind, locality[0])
            for kind in kinds
            for locality in LOCALITIES
        ]
        valid_counts = (1, 2, 3, 6, 7, 10, 19)
        tomorrow = (
            datetime.now(SRI_LANKA_TIMEZONE).date()
            + timedelta(days=1)
        )
        engine_call = AsyncMock(
            return_value={
                "topRecommendations": [],
                "moreRecommendations": [],
                "count": 0,
            }
        )
        dispatch_count = 0

        with patch.object(
            conversation_recommendation_runner,
            "generate_recommendations",
            engine_call,
        ):
            for case_number in range(GENERATED_VALID_CASES):
                pair_count = rng.randint(1, 5)
                selected_pairs = rng.sample(available_pairs, pair_count)
                expected: dict[tuple[TravelRequestKind, str], int] = {}
                extracted_groups: list[dict[str, object]] = []

                for kind, locality in selected_pairs:
                    count = rng.choice(valid_counts)
                    expected[(kind, locality)] = count
                    group: dict[str, object] = {
                        "kind": kind.value,
                        "query": rng.choice(QUERIES[kind]),
                        "searchLocationText": (
                            f"  {locality}  "
                            if rng.randrange(2)
                            else locality
                        ),
                        "requestedCount": count,
                    }

                    if kind is TravelRequestKind.ATTRACTION:
                        group["preferences"] = [
                            rng.choice(
                                (
                                    "scenic places",
                                    "waterfalls",
                                    "no specific preference",
                                )
                            )
                        ]
                    elif kind is TravelRequestKind.HOTEL:
                        group["preferences"] = [
                            rng.choice(
                                (
                                    "boutique hotels",
                                    "quiet accommodation",
                                    "no specific preference",
                                )
                            )
                        ]
                    else:
                        group.update(
                            cuisinePreferences=[
                                rng.choice(
                                    (
                                        "Sri Lankan",
                                        "Indian",
                                        "Italian",
                                    )
                                )
                            ],
                            dietaryRequirements=[
                                rng.choice(
                                    (
                                        "vegetarian",
                                        "vegan",
                                        "halal",
                                        "gluten-free",
                                    )
                                )
                            ],
                            foodAvoidances=[
                                rng.choice(
                                    (
                                        "seafood",
                                        "fast food",
                                        "dairy",
                                    )
                                )
                            ],
                            mealIntents=[
                                rng.choice(
                                    (
                                        "breakfast",
                                        "lunch",
                                        "dinner",
                                        "dessert",
                                    )
                                )
                            ],
                        )

                    extracted_groups.append(group)

                rng.shuffle(extracted_groups)
                initial = ConversationInterpretation.model_validate(
                    {
                        "action": "startNewTrip",
                        "contextPatch": {
                            "requestGroups": {
                                "operation": "add",
                                "groups": extracted_groups,
                            }
                        },
                    }
                )
                context = apply_conversation_interpretation(
                    current_context=TravelContext(),
                    interpretation=initial,
                    traveller_message=(
                        " generated request, please "
                        if case_number % 2
                        else "GENERATED REQUEST!"
                    ),
                )
                context = _verify_group_locations(context)
                data = context.model_dump(mode="python")
                data["trip_start_date"] = tomorrow
                data["trip_end_date"] = tomorrow
                data["daily_start_time"] = (
                    "07:00:00" if case_number % 2 else "09:00:00"
                )
                data["daily_end_time"] = (
                    "21:00:00" if case_number % 2 else "17:00:00"
                )

                data["traveller_type"] = TravellerType.COUPLE
                data["traveller_count"] = 2
                data["travel_modes"] = ["driving"]

                if case_number % 2 == 0:
                    data["starting_location"] = TravelLocation(
                        displayName="Colombo",
                        localityName="Colombo",
                        source=TravelLocationSource.SEARCHED,
                        latitude=6.9271,
                        longitude=79.8612,
                        providerPlaceId="open-meteo-colombo",
                        countryCode="LK",
                        verified=True,
                    )

                context = _awaiting_context(
                    TravelContext.model_validate(data)
                )
                self.assertEqual(
                    {_group_key(group): group.requested_count for group in context.request_groups},
                    expected,
                )

                operation_selector = case_number % 10
                target_key = rng.choice(tuple(expected))

                if operation_selector == 0 and len(expected) < 5:
                    unused_pairs = [
                        pair for pair in available_pairs if pair not in expected
                    ]
                    added_kind, added_locality = rng.choice(unused_pairs)
                    added_count = rng.choice(valid_counts)
                    correction_payload = {
                        "operation": "add",
                        "groups": [
                            {
                                "kind": added_kind.value,
                                "query": rng.choice(QUERIES[added_kind]),
                                "searchLocationText": added_locality,
                                "requestedCount": added_count,
                            }
                        ],
                    }
                    expected[(added_kind, added_locality)] = added_count
                    correction_message = f"also add {added_locality}"
                elif operation_selector == 1 and len(expected) > 1:
                    removed_kind, removed_locality = target_key
                    correction_payload = {
                        "operation": "remove",
                        "targets": [
                            {
                                "kind": removed_kind.value,
                                "searchLocationText": removed_locality,
                            }
                        ],
                    }
                    del expected[target_key]
                    correction_message = (
                        f"looks good except remove {removed_locality}"
                    )
                else:
                    target_kind, target_locality = target_key
                    replacement_count = rng.choice(valid_counts)
                    correction_payload = {
                        "operation": "add",
                        "groups": [
                            {
                                "kind": target_kind.value,
                                "query": rng.choice(QUERIES[target_kind]),
                                "searchLocationText": target_locality,
                                "requestedCount": replacement_count,
                            }
                        ],
                    }
                    expected[target_key] = replacement_count
                    correction_message = (
                        f"okay but make {target_locality} "
                        f"{replacement_count}"
                    )

                correction = ConversationInterpretation.model_validate(
                    {
                        "action": "correctInformation",
                        "contextPatch": {
                            "requestGroups": correction_payload,
                        },
                    }
                )
                engine_call.reset_mock()
                corrected = apply_conversation_interpretation(
                    current_context=context,
                    interpretation=correction,
                    traveller_message=correction_message,
                )
                engine_call.assert_not_awaited()
                self.assertFalse(_is_simple_confirmation(correction_message))
                corrected = _verify_group_locations(corrected)
                corrected = _awaiting_context(corrected)

                actual = {
                    _group_key(group): group.requested_count
                    for group in corrected.request_groups
                }
                self.assertEqual(actual, expected)

                summary = corrected.confirmation_summary
                self.assertIsNotNone(summary)
                assert summary is not None
                for (kind, locality), count in expected.items():
                    self.assertIn(locality, summary)
                    self.assertIn(f"Number requested: {count}", summary)
                    self.assertIn(
                        kind.value.capitalize(),
                        summary,
                    )

                summary_lower = summary.casefold()
                self.assertNotIn("roomcount", summary_lower)
                self.assertNotIn("room_count", summary_lower)
                self.assertNotIn(HOTEL_CATEGORY_ID.casefold(), summary_lower)
                self.assertNotIn(RESTAURANT_CATEGORY_ID.casefold(), summary_lower)
                self.assertNotIn("providerfilterkey", summary_lower)
                self.assertNotIn("open-meteo-", summary_lower)

                serialized = corrected.model_dump(
                    by_alias=True,
                    mode="json",
                )
                serialized_text = json.dumps(
                    serialized,
                    ensure_ascii=False,
                )
                self.assertNotIn("roomCount", serialized_text)
                reloaded = TravelContext.model_validate(serialized)
                self.assertEqual(
                    {
                        _group_key(group): group.requested_count
                        for group in reloaded.request_groups
                    },
                    expected,
                )

                confirmation_phrase = CONFIRMATIONS[
                    case_number % len(CONFIRMATIONS)
                ]
                self.assertTrue(
                    _is_simple_confirmation(confirmation_phrase)
                )
                confirmed = confirm_travel_context(reloaded)
                dispatch_count += 1
                before_calls = engine_call.await_count
                result_groups = await (
                    conversation_recommendation_runner
                    .generate_conversation_recommendations(confirmed)
                )
                expected_calls = len(expected)
                self.assertEqual(
                    engine_call.await_count - before_calls,
                    expected_calls,
                )
                self.assertEqual(len(result_groups), expected_calls)
                recent_calls = engine_call.await_args_list[-expected_calls:]

                for group, result_group, call in zip(
                    confirmed.request_groups,
                    result_groups,
                    recent_calls,
                    strict=True,
                ):
                    request = call.args[0]
                    self.assertEqual(
                        result_group["requestGroupId"],
                        group.id,
                    )
                    self.assertEqual(
                        result_group["requestedCount"],
                        group.requested_count,
                    )
                    self.assertEqual(
                        call.kwargs["requested_count"],
                        group.requested_count,
                    )
                    self.assertEqual(
                        request.location.locality_name,
                        group.search_location.locality_name,
                    )
                    request_payload = request.model_dump(
                        by_alias=True,
                        mode="json",
                    )
                    self.assertNotIn("roomCount", request_payload)
                    self.assertNotIn("providerFilterKey", request_payload)
                    self.assertNotIn("fsqCategoryIds", request_payload)
                    self.assertIsNone(request.visit_duration_minutes)

                    if confirmed.starting_location is None:
                        self.assertIsNone(request.route_origin)
                    else:
                        self.assertEqual(
                            request.route_origin.locality_name,
                            "Colombo",
                        )

        self.assertEqual(dispatch_count, GENERATED_VALID_CASES)

    async def test_generated_unknown_locations_never_reach_provider(
        self,
    ) -> None:
        engine_call = AsyncMock()

        with patch.object(
            conversation_recommendation_runner,
            "generate_recommendations",
            engine_call,
        ):
            for case_number in range(GENERATED_UNKNOWN_LOCATION_CASES):
                context = TravelContext(
                    requestGroups=[
                        TravelRequestGroup(
                            id=f"unknown-{case_number}",
                            kind=TravelRequestKind.RESTAURANT,
                            query="restaurants",
                            searchLocation=TravelLocation(
                                displayName=f"Unknown locality {case_number}",
                                source=TravelLocationSource.SEARCHED,
                                verified=False,
                            ),
                        )
                    ]
                )
                unsafe_context = context.model_copy(
                    update={
                        "stage": TravelContextStage.CONFIRMED,
                        "is_confirmed": True,
                    }
                )

                with self.assertRaises(
                    ConversationRecommendationAdapterError
                ):
                    await (
                        conversation_recommendation_runner
                        .generate_conversation_recommendations(
                            unsafe_context
                        )
                    )

        engine_call.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
