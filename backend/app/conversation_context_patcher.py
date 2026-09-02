from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from uuid import uuid4

from app.conversation_context_requirements import (
    refresh_missing_fields,
)
from app.conversation_extraction_models import (
    CollectionPatchOperation,
    ConversationInterpretation,
    ConversationInterpretationAction,
    DateFieldPatch,
    ExtractedLocationSource,
    PatchOperation,
    RequestGroupReference,
    RequestGroupsPatch,
    ScalarPatchOperation,
    StartingLocationPatch,
    TextFieldPatch,
    TextListPatch,
    TimeFieldPatch,
    TravelModeListPatch,
    TravellerTypeFieldPatch,
)
from app.conversation_models import (
    ConversationDeviceLocation,
    FixedTravelPlace,
    FixedTravelPlaceRole,
    MAXIMUM_REQUESTED_RECOMMENDATIONS,
    TravelContext,
    TravelContextStage,
    TravelLocation,
    TravelLocationSource,
    TravelRequestGroup,
    TravelRequestKind,
)


def _normalize_text_for_matching(text: str) -> str:
    normalized = text.casefold().replace("’", "'").replace("–", "-").replace("—", "-")
    normalized = normalized.replace("'", "")
    normalized = re.sub(r"[^a-z0-9\s-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _normalize_location_identity(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def _request_group_query_identity(group: TravelRequestGroup) -> str:
    return " ".join(group.query.casefold().split())


def _request_group_location_identities(
    group: TravelRequestGroup,
) -> set[str]:
    location = group.search_location

    if location is None:
        return set()

    identities = {
        _normalize_location_identity(value)
        for value in (location.display_name, location.locality_name)
        if isinstance(value, str) and value.strip()
    }
    identities.discard("")
    return identities


def _request_group_matches_location_text(
    group: TravelRequestGroup,
    location_text: str,
) -> bool:
    normalized_target = _normalize_location_identity(location_text)
    return bool(
        normalized_target
        and normalized_target in _request_group_location_identities(group)
    )


def _request_group_locations_match(
    first: TravelRequestGroup,
    second: TravelRequestGroup,
) -> bool:
    first_identities = _request_group_location_identities(first)
    second_identities = _request_group_location_identities(second)
    return bool(
        first_identities
        and second_identities
        and first_identities & second_identities
    )


def _message_explicitly_mentions_party(
    traveller_message: str,
) -> bool:
    normalized = _normalize_text_for_matching(traveller_message)

    if not normalized:
        return False

    if re.search(
        r"\b(?:traveller|travellers|traveler|travelers|person|people|friend|friends|family|couple|partner|solo)\b",
        normalized,
    ):
        return True

    if re.search(r"\b(?:with|and|me and)\s+\d+\b", normalized):
        return True

    if re.search(r"\b(?:with|and)\s+my\b", normalized):
        return True

    if re.search(r"\bof us\b", normalized):
        return True

    return False


def _should_allow_party_patch(
    *,
    current_value: object,
    traveller_message: str,
) -> bool:
    if current_value is None:
        return True

    return _message_explicitly_mentions_party(traveller_message)


def _latest_explicit_request_scope_kinds(message: str) -> set[TravelRequestKind]:
    normalized = _normalize_text_for_matching(message)
    if not normalized:
        return set()

    kinds: set[TravelRequestKind] = set()

    if re.search(r"\b(?:restaurant|restaurants)\b", normalized):
        kinds.add(TravelRequestKind.RESTAURANT)

    if re.search(r"\b(?:attraction|attractions)\b", normalized):
        kinds.add(TravelRequestKind.ATTRACTION)

    if re.search(r"\b(?:hotel|hotels)\b", normalized):
        kinds.add(TravelRequestKind.HOTEL)

    return kinds


def _contains_additive_scope_language(message: str) -> bool:
    normalized = _normalize_text_for_matching(message)
    if not normalized:
        return False

    additive_patterns = (
        r"\b(?:also|add|include|plus|as well)\b",
        r"\bkeep those and\b",
        r"\bkeep .* and .* show\b",
    )

    return any(re.search(pattern, normalized) for pattern in additive_patterns)


def _contains_negative_scope_language(message: str) -> bool:
    normalized = _normalize_text_for_matching(message)
    if not normalized:
        return False

    negative_patterns = (
        r"\b(?:no|without|not)\s+(?:hotel|hotels|restaurant|restaurants|attraction|attractions)\b",
        r"\b(?:hotel|hotels|restaurant|restaurants|attraction|attractions)\s+(?:only|just)\b",
    )

    return any(re.search(pattern, normalized) for pattern in negative_patterns)


def _filter_request_groups_by_latest_explicit_scope(
    *,
    groups: list[dict],
    traveller_message: str,
) -> list[dict]:
    if not groups or not traveller_message:
        return groups

    normalized = _normalize_text_for_matching(traveller_message)
    if not normalized:
        return groups

    explicit_kinds = _latest_explicit_request_scope_kinds(normalized)
    if not explicit_kinds:
        return groups

    additive = _contains_additive_scope_language(normalized)
    negative_kinds = {
        (
            TravelRequestKind.HOTEL
            if re.search(r"\b(?:no|without|not)\s+hotels?\b", normalized)
            else None
        ),
        (
            TravelRequestKind.RESTAURANT
            if re.search(r"\b(?:no|without|not)\s+restaurants?\b", normalized)
            else None
        ),
        (
            TravelRequestKind.ATTRACTION
            if re.search(r"\b(?:no|without|not)\s+attractions?\b", normalized)
            else None
        ),
    }
    negative_kinds = {kind for kind in negative_kinds if kind is not None}

    parsed_groups = [TravelRequestGroup.model_validate(group) for group in groups]

    if additive:
        filtered = [
            group for group in parsed_groups if group.kind not in negative_kinds
        ]
        return [group.model_dump(mode="python") for group in filtered]

    if explicit_kinds & {group.kind for group in parsed_groups}:
        keep_kinds = explicit_kinds - negative_kinds
        filtered = [group for group in parsed_groups if group.kind in keep_kinds]

        if filtered:
            return [group.model_dump(mode="python") for group in filtered]

    if negative_kinds:
        filtered = [
            group for group in parsed_groups if group.kind not in negative_kinds
        ]
        return [group.model_dump(mode="python") for group in filtered]

    return groups


def _explicit_requested_count(
    message: str,
    kind: TravelRequestKind,
) -> int | None:
    normalized = _normalize_text_for_matching(message)
    kind_word = {
        TravelRequestKind.ATTRACTION: r"attractions?",
        TravelRequestKind.RESTAURANT: r"restaurants?",
        TravelRequestKind.HOTEL: r"hotels?",
    }[kind]
    match = re.search(rf"\b(\d+)\s+{kind_word}\b", normalized)

    if match is None:
        return None

    count = int(match.group(1))
    return (
        count
        if 1 <= count <= MAXIMUM_REQUESTED_RECOMMENDATIONS
        else None
    )


def _restore_omitted_explicit_scope_groups(
    *,
    groups: list[dict],
    traveller_message: str,
) -> list[dict]:
    """Do not silently lose an explicitly named recommendation kind.

    GPT remains responsible for semantic extraction. This narrow deterministic
    guard repairs only a missing kind that the traveller named literally. A
    single location shared by the extracted sibling groups can safely be
    shared; otherwise normal missing-location validation asks for clarity.
    """

    if not groups or _contains_negative_scope_language(traveller_message):
        return groups

    explicit_kinds = _latest_explicit_request_scope_kinds(traveller_message)
    parsed_groups = [TravelRequestGroup.model_validate(group) for group in groups]
    present_kinds = {group.kind for group in parsed_groups}
    missing_kinds = explicit_kinds - present_kinds

    if not missing_kinds:
        return groups

    locations = [
        group.search_location
        for group in parsed_groups
        if group.search_location is not None
    ]
    location_identities = {
        tuple(sorted(_request_group_location_identities(group)))
        for group in parsed_groups
        if group.search_location is not None
    }
    shared_location = (
        locations[0].model_copy(deep=True)
        if locations and len(location_identities) == 1
        else None
    )
    query_by_kind = {
        TravelRequestKind.ATTRACTION: "attractions",
        TravelRequestKind.RESTAURANT: "restaurants",
        TravelRequestKind.HOTEL: "hotels",
    }

    for kind in TravelRequestKind:
        if kind not in missing_kinds:
            continue

        parsed_groups.append(
            TravelRequestGroup(
                id=f"request-group-{uuid4().hex}",
                kind=kind,
                query=query_by_kind[kind],
                requested_count=_explicit_requested_count(
                    traveller_message,
                    kind,
                ),
                search_location=shared_location.model_copy(deep=True)
                if shared_location is not None
                else None,
                required=True,
            )
        )

    return [group.model_dump(mode="python") for group in parsed_groups]


def apply_conversation_interpretation(
    *,
    current_context: TravelContext,
    interpretation: ConversationInterpretation,
    traveller_message: str,
    device_location: ConversationDeviceLocation | None = None,
) -> TravelContext:
    if interpretation.action is ConversationInterpretationAction.START_NEW_TRIP:
        context_data = TravelContext(
            schema_version=current_context.schema_version,
            revision=current_context.revision,
        ).model_dump(mode="python")
    else:
        context_data = deepcopy(current_context.model_dump(mode="python"))

    patch = interpretation.context_patch
    changed = False

    if patch.starting_location is not None:
        context_data["starting_location"] = _apply_location_patch(
            current_value=context_data.get("starting_location"),
            patch=patch.starting_location,
            device_location=device_location,
        )
        changed = True

    if patch.final_ending_location is not None:
        context_data["fixed_places"] = _apply_final_ending_location_patch(
            current_places=context_data.get("fixed_places", []),
            patch=patch.final_ending_location,
            device_location=device_location,
        )
        changed = True

    if patch.trip_start_date is not None:
        context_data["trip_start_date"] = _apply_scalar_patch(
            current_value=context_data.get("trip_start_date"),
            patch=patch.trip_start_date,
        )
        changed = True

    if patch.trip_end_date is not None:
        context_data["trip_end_date"] = _apply_scalar_patch(
            current_value=context_data.get("trip_end_date"),
            patch=patch.trip_end_date,
        )
        changed = True

    if (
        patch.trip_start_date is not None
        and patch.trip_end_date is None
        and context_data.get("trip_end_date") is None
    ):
        context_data["trip_end_date"] = context_data.get("trip_start_date")

    if patch.daily_start_time is not None:
        context_data["daily_start_time"] = _apply_scalar_patch(
            current_value=context_data.get("daily_start_time"),
            patch=patch.daily_start_time,
        )
        changed = True

    if patch.daily_end_time is not None:
        context_data["daily_end_time"] = _apply_scalar_patch(
            current_value=context_data.get("daily_end_time"),
            patch=patch.daily_end_time,
        )
        changed = True

    if patch.available_time_description is not None:
        context_data["available_time_description"] = _apply_scalar_patch(
            current_value=context_data.get("available_time_description"),
            patch=patch.available_time_description,
        )
        changed = True

    if patch.traveller_type is not None:
        if _should_allow_party_patch(
            current_value=context_data.get("traveller_type"),
            traveller_message=traveller_message,
        ):
            context_data["traveller_type"] = _apply_scalar_patch(
                current_value=context_data.get("traveller_type"),
                patch=patch.traveller_type,
            )
            changed = True

    if patch.travel_party_description is not None:
        if _should_allow_party_patch(
            current_value=context_data.get("travel_party_description"),
            traveller_message=traveller_message,
        ):
            context_data["travel_party_description"] = _apply_scalar_patch(
                current_value=context_data.get("travel_party_description"),
                patch=patch.travel_party_description,
            )
            changed = True

    if patch.traveller_count is not None:
        if _should_allow_party_patch(
            current_value=context_data.get("traveller_count"),
            traveller_message=traveller_message,
        ):
            context_data["traveller_count"] = _apply_scalar_patch(
                current_value=context_data.get("traveller_count"),
                patch=patch.traveller_count,
            )
            changed = True

    if patch.travel_modes is not None:
        context_data["travel_modes"] = _apply_enum_list_patch(
            current_values=context_data.get("travel_modes", []),
            patch=patch.travel_modes,
        )
        changed = True

    if patch.request_groups is not None:
        context_data["request_groups"] = _apply_request_groups_patch(
            current_groups=context_data.get(
                "request_groups",
                [],
            ),
            patch=patch.request_groups,
        )
        if (
            interpretation.action
            is not ConversationInterpretationAction.CORRECT_INFORMATION
            and current_context.stage
            is not TravelContextStage.AWAITING_CONFIRMATION
            and (
                interpretation.action
                is ConversationInterpretationAction.START_NEW_TRIP
                or patch.request_groups.operation is PatchOperation.REPLACE
            )
        ):
            context_data["request_groups"] = (
                _filter_request_groups_by_latest_explicit_scope(
                    groups=context_data.get("request_groups", []),
                    traveller_message=traveller_message,
                )
            )
            context_data["request_groups"] = (
                _restore_omitted_explicit_scope_groups(
                    groups=context_data.get("request_groups", []),
                    traveller_message=traveller_message,
                )
            )
        changed = True

    if patch.preferences is not None:
        context_data["preferences"] = _apply_text_list_patch(
            current_values=context_data.get("preferences", []),
            patch=patch.preferences,
        )
        changed = True

    if patch.accessibility_needs is not None:
        context_data["accessibility_needs"] = _apply_text_list_patch(
            current_values=context_data.get(
                "accessibility_needs",
                [],
            ),
            patch=patch.accessibility_needs,
        )
        changed = True

    if patch.avoidances is not None:
        context_data["avoidances"] = _apply_text_list_patch(
            current_values=context_data.get("avoidances", []),
            patch=patch.avoidances,
        )
        changed = True

    context_data["uncertainties"] = list(interpretation.uncertainties)
    context_data["missing_fields"] = []

    if interpretation.action is ConversationInterpretationAction.REQUEST_ITINERARY:
        if not context_data.get("requires_complete_itinerary", False):
            context_data["requires_complete_itinerary"] = True
            changed = True

    if changed:
        context_data["stage"] = TravelContextStage.COLLECTING
        context_data["is_confirmed"] = False
        context_data["confirmation_summary"] = None
        context_data["allow_overlong_route"] = False

    updated_context = TravelContext.model_validate(context_data)

    return refresh_missing_fields(updated_context)


def _apply_scalar_patch(
    *,
    current_value: object,
    patch: (
        TextFieldPatch
        | DateFieldPatch
        | TimeFieldPatch
        | TravellerTypeFieldPatch
    ),
) -> object:
    if patch.operation is PatchOperation.CLEAR:
        return None

    return patch.value


def _apply_location_patch(
    *,
    current_value: object,
    patch: StartingLocationPatch,
    device_location: ConversationDeviceLocation | None,
) -> TravelLocation | None:
    if patch.operation is PatchOperation.CLEAR:
        return None

    if patch.source is ExtractedLocationSource.SEARCHED:
        return TravelLocation(
            display_name=patch.search_text or "Unknown location",
            source=TravelLocationSource.SEARCHED,
            verified=False,
        )

    if device_location is not None:
        return TravelLocation(
            display_name="Current location",
            source=TravelLocationSource.CURRENT,
            latitude=device_location.latitude,
            longitude=device_location.longitude,
            verified=True,
        )

    return TravelLocation(
        display_name="Current location",
        source=TravelLocationSource.CURRENT,
        verified=False,
    )


def _apply_final_ending_location_patch(
    *,
    current_places: list[dict],
    patch: StartingLocationPatch,
    device_location: ConversationDeviceLocation | None,
) -> list[dict]:
    places = [FixedTravelPlace.model_validate(place) for place in current_places]

    retained_places = [
        place
        for place in places
        if place.role is not FixedTravelPlaceRole.END_POINT
    ]

    if patch.operation is PatchOperation.CLEAR:
        return [place.model_dump(mode="python") for place in retained_places]

    existing_end_point = next(
        (
            place
            for place in places
            if place.role is FixedTravelPlaceRole.END_POINT
        ),
        None,
    )

    location = _apply_location_patch(
        current_value=(
            existing_end_point.location.model_dump(mode="python")
            if existing_end_point is not None
            else None
        ),
        patch=patch,
        device_location=device_location,
    )

    if location is None:
        return [place.model_dump(mode="python") for place in retained_places]

    end_point = FixedTravelPlace(
        id=(
            existing_end_point.id
            if existing_end_point is not None
            else f"final-end-{uuid4().hex}"
        ),
        name=location.display_name,
        role=FixedTravelPlaceRole.END_POINT,
        location=location,
        confirmed=True,
    )

    return [
        *[place.model_dump(mode="python") for place in retained_places],
        end_point.model_dump(mode="python"),
    ]


def _apply_text_list_patch(
    *,
    current_values: list[str],
    patch: TextListPatch,
) -> list[str]:
    values = list(current_values)

    if patch.operation is PatchOperation.CLEAR:
        return []

    if patch.operation is PatchOperation.REPLACE:
        return _unique_strings(patch.values)

    if patch.operation is PatchOperation.ADD:
        return _unique_strings([*values, *patch.values])

    remove_values = {value.casefold() for value in patch.values}

    return [value for value in values if value.casefold() not in remove_values]


def _apply_enum_list_patch(
    *,
    current_values: list[str],
    patch: TravelModeListPatch,
) -> list[str]:
    patch_values = [value.value for value in patch.values]

    if patch.operation is PatchOperation.CLEAR:
        return []

    if patch.operation is PatchOperation.REPLACE:
        return _unique_strings(patch_values)

    if patch.operation is PatchOperation.ADD:
        return _unique_strings([*current_values, *patch_values])

    remove_values = {value.casefold() for value in patch_values}

    return [value for value in current_values if value.casefold() not in remove_values]


def _apply_request_groups_patch(
    *,
    current_groups: list[dict],
    patch: RequestGroupsPatch,
) -> list[dict]:
    groups = [TravelRequestGroup.model_validate(group) for group in current_groups]

    if patch.operation is PatchOperation.CLEAR:
        return []

    if patch.operation is PatchOperation.ADD:
        additions = [_create_request_group(group) for group in patch.groups]

        return [
            group.model_dump(mode="python")
            for group in _merge_request_groups(
                groups,
                additions,
            )
        ]

    target_indexes = _resolve_target_indexes(
        groups=groups,
        targets=patch.targets,
    )

    if patch.operation is PatchOperation.REMOVE:
        return [
            group.model_dump(mode="python")
            for index, group in enumerate(groups)
            if index not in target_indexes
        ]

    replacements = [_create_request_group(group) for group in patch.groups]

    if len(target_indexes) == 1 and len(replacements) == 1:
        target_index = next(iter(target_indexes))
        target_group = groups[target_index]
        replacement = replacements[0]

        if target_group.kind is replacement.kind:
            replacements = [
                _merge_same_kind_replacement(
                    existing=target_group,
                    replacement=replacement,
                )
            ]

    remaining_groups = [
        group for index, group in enumerate(groups) if index not in target_indexes
    ]

    return [
        group.model_dump(mode="python")
        for group in _merge_request_groups(
            remaining_groups,
            replacements,
        )
    ]


def _create_request_group(
    extracted_group,
) -> TravelRequestGroup:
    search_location = (
        TravelLocation(
            display_name=extracted_group.search_location_text,
            source=TravelLocationSource.SEARCHED,
            verified=False,
        )
        if extracted_group.search_location_text is not None
        else None
    )

    return TravelRequestGroup(
        id=f"request-group-{uuid4().hex}",
        kind=extracted_group.kind,
        query=extracted_group.query,
        preferences=extracted_group.preferences,
        cuisine_preferences=extracted_group.cuisine_preferences,
        dietary_requirements=extracted_group.dietary_requirements,
        food_avoidances=extracted_group.food_avoidances,
        meal_intents=extracted_group.meal_intents,
        requested_count=extracted_group.requested_count,
        search_location=search_location,
        required=True,
    )


def _resolve_target_indexes(
    *,
    groups: list[TravelRequestGroup],
    targets: list[RequestGroupReference],
) -> set[int]:
    matched_indexes: set[int] = set()

    for target in targets:
        if target.ordinal is not None:
            index = target.ordinal - 1

            if 0 <= index < len(groups):
                matched_indexes.add(index)

        for index, group in enumerate(groups):
            kind_matches = target.kind is None or group.kind is target.kind

            query_matches = (
                target.query is None
                or target.query.casefold() in group.query.casefold()
            )

            location_matches = (
                target.search_location_text is None
                or _request_group_matches_location_text(
                    group,
                    target.search_location_text,
                )
            )

            if kind_matches and query_matches and location_matches:
                matched_indexes.add(index)

    return matched_indexes


def _merge_request_groups(
    existing: list[TravelRequestGroup],
    additions: list[TravelRequestGroup],
) -> list[TravelRequestGroup]:
    merged = list(existing)

    for addition in additions:
        duplicate_index = _request_group_merge_index(
            groups=merged,
            addition=addition,
        )

        if duplicate_index is None:
            merged.append(addition)
            continue

        existing_group = merged[duplicate_index]

        merged[duplicate_index] = existing_group.model_copy(
            update={
                "preferences": _unique_strings(
                    [
                        *existing_group.preferences,
                        *addition.preferences,
                    ]
                ),
                "cuisine_preferences": _unique_strings(
                    [
                        *existing_group.cuisine_preferences,
                        *addition.cuisine_preferences,
                    ]
                ),
                "dietary_requirements": _unique_strings(
                    [
                        *existing_group.dietary_requirements,
                        *addition.dietary_requirements,
                    ]
                ),
                "food_avoidances": _unique_strings(
                    [
                        *existing_group.food_avoidances,
                        *addition.food_avoidances,
                    ]
                ),
                "meal_intents": _unique_strings(
                    [
                        *existing_group.meal_intents,
                        *addition.meal_intents,
                    ]
                ),
                "requested_count": (
                    addition.requested_count
                    if addition.requested_count is not None
                    else existing_group.requested_count
                ),
                "search_location": (
                    _merge_search_location(
                        existing_group,
                        addition,
                    )
                ),
                "required": True,
            }
        )

    return merged


def _request_group_merge_index(
    *,
    groups: list[TravelRequestGroup],
    addition: TravelRequestGroup,
) -> int | None:
    exact_query_indexes = [
        index
        for index, group in enumerate(groups)
        if (
            group.kind is addition.kind
            and _request_group_query_identity(group)
            == _request_group_query_identity(addition)
        )
    ]

    addition_has_location = bool(
        _request_group_location_identities(addition)
    )

    if addition_has_location:
        exact_location_indexes = [
            index
            for index in exact_query_indexes
            if _request_group_locations_match(groups[index], addition)
        ]

        if len(exact_location_indexes) == 1:
            return exact_location_indexes[0]

        unlocated_indexes = [
            index
            for index in exact_query_indexes
            if not _request_group_location_identities(groups[index])
        ]

        if len(unlocated_indexes) == 1:
            return unlocated_indexes[0]

        if _is_count_only_group_update(addition):
            same_kind_location_indexes = [
                index
                for index, group in enumerate(groups)
                if (
                    group.kind is addition.kind
                    and _request_group_locations_match(group, addition)
                )
            ]

            if len(same_kind_location_indexes) == 1:
                return same_kind_location_indexes[0]

        return None

    if len(exact_query_indexes) == 1:
        return exact_query_indexes[0]

    if len(exact_query_indexes) > 1:
        raise ValueError(
            "a request-group update without a locality is ambiguous"
        )

    if _is_count_only_group_update(addition):
        same_kind_indexes = [
            index
            for index, group in enumerate(groups)
            if group.kind is addition.kind
        ]

        if len(same_kind_indexes) == 1:
            return same_kind_indexes[0]

        if len(same_kind_indexes) > 1:
            raise ValueError(
                "a count correction requires a locality when multiple "
                "request groups have the same kind"
            )

    return None


def _merge_same_kind_replacement(
    *,
    existing: TravelRequestGroup,
    replacement: TravelRequestGroup,
) -> TravelRequestGroup:
    """Preserve facts omitted by a one-group same-kind correction."""

    return existing.model_copy(
        update={
            "query": replacement.query,
            "preferences": (
                replacement.preferences
                if replacement.preferences
                else existing.preferences
            ),
            "cuisine_preferences": (
                replacement.cuisine_preferences
                if replacement.cuisine_preferences
                else existing.cuisine_preferences
            ),
            "dietary_requirements": (
                replacement.dietary_requirements
                if replacement.dietary_requirements
                else existing.dietary_requirements
            ),
            "food_avoidances": (
                replacement.food_avoidances
                if replacement.food_avoidances
                else existing.food_avoidances
            ),
            "meal_intents": (
                replacement.meal_intents
                if replacement.meal_intents
                else existing.meal_intents
            ),
            "requested_count": (
                replacement.requested_count
                if replacement.requested_count is not None
                else existing.requested_count
            ),
            "search_location": (
                replacement.search_location
                if replacement.search_location is not None
                else existing.search_location
            ),
            "required": True,
        }
    )


def _merge_search_location(
    existing: TravelRequestGroup,
    addition: TravelRequestGroup,
) -> TravelLocation | None:
    existing_location = existing.search_location
    addition_location = addition.search_location

    if addition_location is None:
        return existing_location

    if existing_location is None:
        return addition_location

    if (
        _request_group_locations_match(existing, addition)
        and existing_location.verified
        and not addition_location.verified
    ):
        return existing_location

    return addition_location


def _is_count_only_group_update(
    group: TravelRequestGroup,
) -> bool:
    return (
        group.requested_count is not None
        and not group.preferences
        and not group.cuisine_preferences
        and not group.dietary_requirements
        and not group.food_avoidances
        and not group.meal_intents
    )


def _unique_strings(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized = value.strip()
        comparison_value = normalized.casefold()

        if not normalized or comparison_value in seen:
            continue

        seen.add(comparison_value)
        unique_values.append(normalized)

    return unique_values
