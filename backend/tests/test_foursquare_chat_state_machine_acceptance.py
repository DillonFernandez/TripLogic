"""Long fixed-seed mutation sequences for Foursquare chat acceptance."""

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
    FixedTravelPlace,
    FixedTravelPlaceRole,
    TravelContext,
    TravelContextStage,
    TravelLocation,
    TravelLocationSource,
    TravelRequestGroup,
    TravelRequestKind,
    TravellerType,
)
from app.conversation_router import _is_simple_confirmation  # noqa: E402
from app.foursquare_categories import (  # noqa: E402
    HOTEL_CATEGORY_ID,
    RESTAURANT_CATEGORY_ID,
)


STATE_MACHINE_SEQUENCES = 500
MINIMUM_TRANSITIONS = 20
MAXIMUM_TRANSITIONS = 50
STATE_MACHINE_SEED = 17_019_500
SRI_LANKA_TIMEZONE = ZoneInfo("Asia/Colombo")

LOCALITIES: tuple[tuple[str, float, float], ...] = (
    ("Kandy", 7.2906, 80.6337),
    ("Galle", 6.0329, 80.2168),
    ("Ella", 6.8667, 81.0466),
    ("Sigiriya", 7.9570, 80.7603),
    ("Nuwara Eliya", 6.9497, 80.7891),
    ("Negombo", 7.2083, 79.8358),
    ("Haputale", 6.7667, 80.9597),
    ("Dehiwala", 6.8519, 79.8653),
    ("Jaffna", 9.6615, 80.0255),
    ("මහනුවර", 7.2906, 80.6337),
)

QUERY_BY_KIND = {
    TravelRequestKind.ATTRACTION: "attractions",
    TravelRequestKind.RESTAURANT: "restaurants",
    TravelRequestKind.HOTEL: "hotels",
}

PREFERENCE_FIELDS = {
    TravelRequestKind.ATTRACTION: ("preferences", "scenic places"),
    TravelRequestKind.HOTEL: ("preferences", "boutique hotels"),
    TravelRequestKind.RESTAURANT: (
        "cuisinePreferences",
        "Sri Lankan",
    ),
}

CLEAN_CONFIRMATIONS = (
    "yes",
    "okay",
    "OK!",
    "go ahead",
    "looks good",
    "sounds good",
    "proceed please",
)

CORRECTION_PREFIXES = (
    "yes but",
    "okay but",
    "looks good except",
)


def _location(name: str) -> TravelLocation:
    display_name, latitude, longitude = next(
        locality for locality in LOCALITIES if locality[0] == name
    )
    return TravelLocation(
        displayName=display_name,
        localityName=display_name,
        source=TravelLocationSource.SEARCHED,
        latitude=latitude,
        longitude=longitude,
        providerPlaceId=f"open-meteo-{display_name}",
        countryCode="LK",
        verified=True,
    )


def _group_key(group: TravelRequestGroup) -> tuple[TravelRequestKind, str]:
    assert group.search_location is not None
    return group.kind, group.search_location.display_name


def _groups_by_key(
    context: TravelContext,
) -> dict[tuple[TravelRequestKind, str], TravelRequestGroup]:
    return {_group_key(group): group for group in context.request_groups}


def _group_fact_dump(group: TravelRequestGroup) -> dict[str, object]:
    return group.model_dump(mode="json")


def _verify_all_group_locations(context: TravelContext) -> TravelContext:
    data = context.model_dump(mode="python")
    data["request_groups"] = [
        group.model_copy(
            update={
                "search_location": _location(
                    group.search_location.display_name
                )
            }
        ).model_dump(mode="python")
        for group in context.request_groups
    ]
    return refresh_missing_fields(TravelContext.model_validate(data))


def _awaiting(context: TravelContext) -> TravelContext:
    refreshed = refresh_missing_fields(context)
    if not refreshed.is_ready_for_confirmation:
        raise AssertionError(
            f"state is not confirmable: {refreshed.missing_fields!r}"
        )
    summary = build_confirmation_summary(refreshed)
    data = refreshed.model_dump(mode="python")
    data.update(
        stage=TravelContextStage.AWAITING_CONFIRMATION,
        is_confirmed=False,
        confirmation_summary=summary,
    )
    return TravelContext.model_validate(data)


def _interpretation(request_groups_patch: dict[str, object]) -> ConversationInterpretation:
    return ConversationInterpretation.model_validate(
        {
            "action": "correctInformation",
            "contextPatch": {"requestGroups": request_groups_patch},
        }
    )


class FoursquareChatStateMachineAcceptanceTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_long_generated_mutation_sequences(self) -> None:
        rng = random.Random(STATE_MACHINE_SEED)
        all_pairs = [
            (kind, locality[0])
            for kind in TravelRequestKind
            for locality in LOCALITIES
        ]
        tomorrow = (
            datetime.now(SRI_LANKA_TIMEZONE).date()
            + timedelta(days=1)
        )
        provider = AsyncMock(
            return_value={
                "topRecommendations": [],
                "moreRecommendations": [],
                "count": 0,
            }
        )
        total_transitions = 0
        dispatches = 0

        with patch.object(
            conversation_recommendation_runner,
            "generate_recommendations",
            provider,
        ):
            for sequence_number in range(STATE_MACHINE_SEQUENCES):
                initial_pairs = rng.sample(all_pairs, rng.randint(1, 3))
                groups = [
                    TravelRequestGroup(
                        id=f"sequence-{sequence_number}-group-{index}",
                        kind=kind,
                        query=QUERY_BY_KIND[kind],
                        requestedCount=rng.randint(1, 19),
                        searchLocation=_location(locality),
                    )
                    for index, (kind, locality) in enumerate(initial_pairs)
                ]
                origin = (
                    _location("Kandy")
                    if sequence_number % 2 == 0
                    else None
                )
                final_place = (
                    FixedTravelPlace(
                        id=f"sequence-{sequence_number}-end",
                        name="Galle",
                        role=FixedTravelPlaceRole.END_POINT,
                        location=_location("Galle"),
                        confirmed=True,
                    )
                    if sequence_number % 3 == 0
                    else None
                )
                context = _awaiting(
                    TravelContext(
                        startingLocation=origin,
                        tripStartDate=tomorrow,
                        tripEndDate=tomorrow,
                        dailyStartTime="07:00:00",
                        dailyEndTime="21:00:00",
                        travellerType=TravellerType.COUPLE,
                        travellerCount=2,
                        travelModes=["driving"],
                        requestGroups=groups,
                        fixedPlaces=(
                            [final_place]
                            if final_place is not None
                            else []
                        ),
                    )
                )
                transition_count = rng.randint(
                    MINIMUM_TRANSITIONS,
                    MAXIMUM_TRANSITIONS,
                )

                for transition_number in range(transition_count):
                    total_transitions += 1
                    before = _groups_by_key(context)
                    before_facts = {
                        key: _group_fact_dump(group)
                        for key, group in before.items()
                    }
                    operation = rng.randrange(6)
                    if (
                        (operation == 0 and len(before) >= 6)
                        or (operation == 1 and len(before) <= 1)
                    ):
                        operation = 5
                    target_key = rng.choice(tuple(before))
                    target = before[target_key]
                    correction_prefix = CORRECTION_PREFIXES[
                        transition_number % len(CORRECTION_PREFIXES)
                    ]
                    expected_count: int | None = None
                    expected_preference: tuple[str, str] | None = None

                    if operation == 0 and len(before) < 6:
                        unused_pairs = [
                            pair for pair in all_pairs if pair not in before
                        ]
                        added_kind, added_locality = rng.choice(unused_pairs)
                        new_count = rng.randint(1, 19)
                        interpretation = _interpretation(
                            {
                                "operation": "add",
                                "groups": [
                                    {
                                        "kind": added_kind.value,
                                        "query": QUERY_BY_KIND[added_kind],
                                        "searchLocationText": added_locality,
                                        "requestedCount": new_count,
                                    }
                                ],
                            }
                        )
                        message = (
                            f"{correction_prefix} also add "
                            f"{new_count} in {added_locality}"
                        )
                        changed_key = (added_kind, added_locality)
                        expected_operation = "add"
                    elif operation == 1 and len(before) > 1:
                        interpretation = _interpretation(
                            {
                                "operation": "remove",
                                "targets": [
                                    {
                                        "kind": target.kind.value,
                                        "searchLocationText": target_key[1],
                                    }
                                ],
                            }
                        )
                        message = (
                            f"{correction_prefix} remove {target_key[1]}"
                        )
                        changed_key = target_key
                        expected_operation = "remove"
                    elif operation == 2:
                        replacement_count = rng.randint(1, 19)
                        expected_count = replacement_count
                        interpretation = _interpretation(
                            {
                                "operation": "add",
                                "groups": [
                                    {
                                        "kind": target.kind.value,
                                        "query": target.query,
                                        "searchLocationText": target_key[1],
                                        "requestedCount": replacement_count,
                                    }
                                ],
                            }
                        )
                        message = (
                            f"{correction_prefix} make {target_key[1]} "
                            f"count {replacement_count}"
                        )
                        changed_key = target_key
                        expected_operation = "count"
                    elif operation == 3:
                        field_name, preference = PREFERENCE_FIELDS[target.kind]
                        preference_value = (
                            f"{preference} {transition_number % 4}"
                        )
                        expected_preference = (field_name, preference_value)
                        interpretation = _interpretation(
                            {
                                "operation": "add",
                                "groups": [
                                    {
                                        "kind": target.kind.value,
                                        "query": target.query,
                                        "searchLocationText": target_key[1],
                                        field_name: [
                                            preference_value
                                        ],
                                    }
                                ],
                            }
                        )
                        message = (
                            f"{correction_prefix} add a preference for "
                            f"{target_key[1]}"
                        )
                        changed_key = target_key
                        expected_operation = "preference"
                    elif operation == 4:
                        candidate_localities = [
                            locality[0]
                            for locality in LOCALITIES
                            if (target.kind, locality[0]) not in before
                        ]

                        if candidate_localities:
                            replacement_locality = rng.choice(
                                candidate_localities
                            )
                            interpretation = _interpretation(
                                {
                                    "operation": "replace",
                                    "targets": [
                                        {
                                            "kind": target.kind.value,
                                            "searchLocationText": target_key[1],
                                        }
                                    ],
                                    "groups": [
                                        {
                                            "kind": target.kind.value,
                                            "query": target.query,
                                            "searchLocationText": replacement_locality,
                                        }
                                    ],
                                }
                            )
                            message = (
                                f"{correction_prefix} use "
                                f"{replacement_locality} instead"
                            )
                            changed_key = (
                                target.kind,
                                replacement_locality,
                            )
                            expected_operation = "location"
                        else:
                            operation = 5

                    if operation == 5:
                        interpretation = _interpretation(
                            {
                                "operation": "add",
                                "groups": [
                                    {
                                        "kind": target.kind.value,
                                        "query": target.query,
                                        "searchLocationText": target_key[1],
                                        "requestedCount": target.requested_count,
                                    }
                                ],
                            }
                        )
                        message = (
                            f"{correction_prefix} keep {target_key[1]} "
                            "the same"
                        )
                        changed_key = target_key
                        expected_operation = "duplicate"

                    provider.reset_mock()
                    self.assertFalse(_is_simple_confirmation(message))
                    updated = apply_conversation_interpretation(
                        current_context=context,
                        interpretation=interpretation,
                        traveller_message=message,
                    )
                    provider.assert_not_awaited()
                    updated = _verify_all_group_locations(updated)
                    after = _groups_by_key(updated)
                    self.assertEqual(len(after), len(updated.request_groups))

                    if expected_operation == "add":
                        self.assertEqual(set(after), set(before) | {changed_key})
                        for key in before:
                            self.assertEqual(
                                _group_fact_dump(after[key]),
                                before_facts[key],
                            )
                    elif expected_operation == "remove":
                        self.assertEqual(set(after), set(before) - {changed_key})
                        for key in after:
                            self.assertEqual(
                                _group_fact_dump(after[key]),
                                before_facts[key],
                            )
                    elif expected_operation == "location":
                        self.assertNotIn(
                            target_key,
                            after,
                            msg=(
                                f"seed={STATE_MACHINE_SEED} "
                                f"sequence={sequence_number} "
                                f"transition={transition_number} "
                                f"target={target_key!r} "
                                f"replacement={changed_key!r} "
                                f"before={tuple(before)!r} "
                                f"after={tuple(after)!r}"
                            ),
                        )
                        self.assertIn(changed_key, after)
                        replacement = after[changed_key]
                        self.assertEqual(
                            replacement.requested_count,
                            target.requested_count,
                        )
                        self.assertEqual(
                            replacement.preferences,
                            target.preferences,
                        )
                        self.assertEqual(
                            replacement.cuisine_preferences,
                            target.cuisine_preferences,
                        )
                        for key in before:
                            if key != target_key:
                                self.assertEqual(
                                    _group_fact_dump(after[key]),
                                    before_facts[key],
                                )
                    elif expected_operation == "count":
                        self.assertEqual(
                            after[changed_key].requested_count,
                            expected_count,
                        )
                        for key in before:
                            if key != changed_key:
                                self.assertEqual(
                                    _group_fact_dump(after[key]),
                                    before_facts[key],
                                )
                        self.assertEqual(
                            after[changed_key].search_location,
                            target.search_location,
                        )
                    elif expected_operation == "preference":
                        assert expected_preference is not None
                        field_name, preference_value = expected_preference
                        model_field_name = {
                            "preferences": "preferences",
                            "cuisinePreferences": "cuisine_preferences",
                        }[field_name]
                        self.assertIn(
                            preference_value,
                            getattr(after[changed_key], model_field_name),
                        )
                        for key in before:
                            if key != changed_key:
                                self.assertEqual(
                                    _group_fact_dump(after[key]),
                                    before_facts[key],
                                )
                    elif expected_operation == "duplicate":
                        self.assertEqual(
                            {
                                key: _group_fact_dump(group)
                                for key, group in after.items()
                            },
                            before_facts,
                        )

                    if transition_number % 7 == 0:
                        data = updated.model_dump(mode="python")
                        data["request_groups"] = list(
                            reversed(data["request_groups"])
                        )
                        updated = TravelContext.model_validate(data)

                    serialized = updated.model_dump(
                        by_alias=True,
                        mode="json",
                    )
                    serialized_text = json.dumps(
                        serialized,
                        ensure_ascii=False,
                    )
                    self.assertNotIn("roomCount", serialized_text)
                    context = _awaiting(
                        TravelContext.model_validate(serialized)
                    )
                    summary = context.confirmation_summary
                    assert summary is not None
                    self.assertIn("Please confirm", summary)
                    self.assertNotIn(HOTEL_CATEGORY_ID, summary)
                    self.assertNotIn(RESTAURANT_CATEGORY_ID, summary)
                    self.assertNotIn("providerFilterKey", summary)
                    self.assertNotIn("open-meteo-", summary)

                    for group in context.request_groups:
                        self.assertIsNotNone(group.search_location)
                        self.assertTrue(group.search_location.verified)
                        self.assertGreaterEqual(group.requested_count, 1)
                        self.assertLessEqual(group.requested_count, 19)
                        self.assertIn(
                            f"Number requested: {group.requested_count}",
                            summary,
                        )
                        self.assertIn(
                            group.search_location.display_name,
                            summary,
                        )

                provider.reset_mock()
                confirmation = CLEAN_CONFIRMATIONS[
                    sequence_number % len(CLEAN_CONFIRMATIONS)
                ]
                self.assertTrue(_is_simple_confirmation(confirmation))
                confirmed = confirm_travel_context(context)
                dispatches += 1
                results = await (
                    conversation_recommendation_runner
                    .generate_conversation_recommendations(confirmed)
                )
                self.assertEqual(len(results), len(confirmed.request_groups))
                self.assertEqual(
                    provider.await_count,
                    len(confirmed.request_groups),
                )

                for group, result, call in zip(
                    confirmed.request_groups,
                    results,
                    provider.await_args_list,
                    strict=True,
                ):
                    request = call.args[0]
                    self.assertEqual(
                        result["requestedCount"],
                        group.requested_count,
                    )
                    self.assertEqual(
                        request.location.locality_name,
                        group.search_location.locality_name,
                    )
                    self.assertIsNone(request.visit_duration_minutes)
                    self.assertEqual(result["result"]["count"], 0)
                    self.assertEqual(
                        result["result"]["topRecommendations"],
                        [],
                    )
                    self.assertEqual(
                        result["result"]["moreRecommendations"],
                        [],
                    )

                    if confirmed.starting_location is None:
                        self.assertIsNone(request.route_origin)
                    else:
                        self.assertEqual(
                            request.route_origin.locality_name,
                            "Kandy",
                        )

        self.assertEqual(dispatches, STATE_MACHINE_SEQUENCES)
        self.assertGreaterEqual(
            total_transitions,
            STATE_MACHINE_SEQUENCES * MINIMUM_TRANSITIONS,
        )
        print(f"STATE_MACHINE_TRANSITIONS={total_transitions}")


if __name__ == "__main__":
    unittest.main()
