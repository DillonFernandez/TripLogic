"""Contracts for Trip Logic's immutable Foursquare taxonomy registry."""

from __future__ import annotations

import re
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.foursquare_categories import (  # noqa: E402
    ACTIVE_ATTRACTION_CATEGORY_IDS,
    ALL_FOURSQUARE_CATEGORIES,
    ATTRACTION_INTENT_ALIASES,
    ATTRACTION_CATEGORIES,
    CATEGORIES_BY_ID,
    FoursquareCategoryFamily,
    GENERIC_ATTRACTION_GROUPS,
    HOTEL_CATEGORY_ID,
    INTENT_CATEGORY_PRESETS,
    RESTAURANT_CATEGORY_ID,
    resolve_attraction_intent_presets,
)


EXPECTED_ATTRACTION_IDS_BY_NAME = {
    "Museum": "4bf58dd8d48988d181941735",
    "Art Museum": "4bf58dd8d48988d18f941735",
    "History Museum": "4bf58dd8d48988d190941735",
    "Science Museum": "4bf58dd8d48988d191941735",
    "Art Gallery": "4bf58dd8d48988d1e2931735",
    "Cultural Center": "52e81612bcbc57f1066b7a32",
    "Performing Arts Venue": "4bf58dd8d48988d1f2931735",
    "Amphitheater": "56aa371be4b08b9a8d5734db",
    "Concert Hall": "5032792091d4c4b30a586d5c",
    "Opera House": "4bf58dd8d48988d136941735",
    "Theater": "4bf58dd8d48988d137941735",
    "Exhibit": "56aa371be4b08b9a8d573532",
    "Public Art": "507c8c4091d498d9fc8c67a9",
    "Outdoor Sculpture": "52e81612bcbc57f1066b79ed",
    "Street Art": "52e81612bcbc57f1066b79ee",
    "Sculpture Garden": "4bf58dd8d48988d166941735",
    "Historic and Protected Site": "4deefb944765f83613cdba6e",
    "Monument": "4bf58dd8d48988d12d941735",
    "Memorial Site": "5642206c498e4bfca532186c",
    "Palace": "52e81612bcbc57f1066b7a14",
    "Castle": "50aaa49e4b90af0d42d5de11",
    "Lighthouse": "4bf58dd8d48988d15d941735",
    "Bridge": "4bf58dd8d48988d1df941735",
    "Fountain": "56aa371be4b08b9a8d573547",
    "Spiritual Center": "4bf58dd8d48988d131941735",
    "Buddhist Temple": "52e81612bcbc57f1066b7a3e",
    "Hindu Temple": "52e81612bcbc57f1066b7a3f",
    "Church": "4bf58dd8d48988d132941735",
    "Mosque": "4bf58dd8d48988d138941735",
    "Shrine": "4eb1d80a4b900d56c88a45ff",
    "Monastery": "52e81612bcbc57f1066b7a40",
    "Temple": "4bf58dd8d48988d13a941735",
    "Confucian Temple": "56aa371be4b08b9a8d5734fc",
    "Sikh Temple": "5bae9231bedf3950379f89c9",
    "Synagogue": "4bf58dd8d48988d139941735",
    "Scenic Lookout": "4bf58dd8d48988d165941735",
    "Hill": "5bae9231bedf3950379f89cd",
    "Waterfront": "56aa371be4b08b9a8d5734c3",
    "Botanical Garden": "52e81612bcbc57f1066b7a22",
    "Garden": "4bf58dd8d48988d15a941735",
    "Park": "4bf58dd8d48988d163941735",
    "National Park": "52e81612bcbc57f1066b7a21",
    "Natural Park": "63be6904847c3692a84b9be0",
    "State or Provincial Park": "5bae9231bedf3950379f89d0",
    "Urban Park": "63be6904847c3692a84b9be1",
    "Mountain": "4eb1d4d54b900d56c88a45fc",
    "Waterfall": "56aa371be4b08b9a8d573560",
    "Beach": "4bf58dd8d48988d1e2941735",
    "Lake": "4bf58dd8d48988d161941735",
    "River": "4eb1d4dd4b900d56c88a45fd",
    "Cave": "56aa371be4b08b9a8d573511",
    "Forest": "52e81612bcbc57f1066b7a23",
    "Island": "50aaa4314b90af0d42d5de10",
    "Hot Spring": "4bf58dd8d48988d160941735",
    "Bay": "56aa371be4b08b9a8d573544",
    "Reservoir": "56aa371be4b08b9a8d573541",
    "Dam": "5fac018b99ce226e27fe7573",
    "Harbor or Marina": "4bf58dd8d48988d1e0941735",
    "Nature Preserve": "52e81612bcbc57f1066b7a13",
    "Zoo": "4bf58dd8d48988d17b941735",
    "Aquarium": "4fceea171983d5d06c3e9823",
    "Hiking Trail": "4bf58dd8d48988d159941735",
    "Bike Trail": "56aa371be4b08b9a8d57355e",
    "Dive Spot": "52e81612bcbc57f1066b7a12",
    "Surf Spot": "4bf58dd8d48988d1e3941735",
    "Rock Climbing Spot": "50328a4b91d4c4b30a586d6b",
    "Campground": "4bf58dd8d48988d1e4941735",
    "Amusement Park": "4bf58dd8d48988d182941735",
    "Attraction": "5109983191d435c0d71c2bb1",
    "Water Park": "4bf58dd8d48988d193941735",
    "Arcade": "4bf58dd8d48988d1e1931735",
    "Escape Room": "5f2c2834b6d05514c704451e",
    "Go Kart Track": "52e81612bcbc57f1066b79ea",
    "Mini Golf Course": "52e81612bcbc57f1066b79eb",
    "Planetarium": "4bf58dd8d48988d192941735",
    "Observatory": "5744ccdfe4b0c0459246b4d9",
}

EXPECTED_GENERIC_GROUP_NAMES = {
    "heritage_and_culture": (
        "Museum",
        "Art Gallery",
        "Cultural Center",
        "Public Art",
        "Historic and Protected Site",
        "Monument",
        "Palace",
        "Spiritual Center",
    ),
    "landscapes_and_water": (
        "Scenic Lookout",
        "Waterfall",
        "Beach",
        "Mountain",
        "Cave",
        "Lake",
        "Forest",
        "Waterfront",
    ),
    "parks_wildlife_and_outdoors": (
        "Botanical Garden",
        "National Park",
        "Natural Park",
        "Nature Preserve",
        "Hiking Trail",
        "Zoo",
        "Aquarium",
        "Island",
    ),
    "family_and_learning": (
        "Amusement Park",
        "Water Park",
        "Planetarium",
        "Observatory",
    ),
}

EXPECTED_INTENT_PRESET_NAMES = {
    "temples": (
        "Buddhist Temple",
        "Hindu Temple",
        "Temple",
        "Shrine",
        "Monastery",
    ),
    "historic_places": (
        "Historic and Protected Site",
        "Monument",
        "Memorial Site",
        "Palace",
        "Castle",
        "Lighthouse",
    ),
    "museums": ("Museum",),
    "art_galleries": ("Art Gallery",),
    "waterfalls": ("Waterfall",),
    "beaches": ("Beach",),
    "wildlife": (
        "Nature Preserve",
        "National Park",
        "Natural Park",
        "Zoo",
        "Aquarium",
    ),
    "nature": (
        "Nature Preserve",
        "National Park",
        "Natural Park",
        "Forest",
        "Mountain",
        "Waterfall",
        "Lake",
        "Cave",
    ),
    "scenic_places": (
        "Scenic Lookout",
        "Mountain",
        "Hill",
        "Waterfall",
        "Waterfront",
    ),
    "parks": (
        "National Park",
        "Natural Park",
        "State or Provincial Park",
        "Urban Park",
    ),
    "botanical_gardens": ("Botanical Garden",),
    "hiking": (
        "Hiking Trail",
        "Mountain",
        "Nature Preserve",
    ),
    "family_attractions": (
        "Amusement Park",
        "Water Park",
        "Zoo",
        "Aquarium",
        "Planetarium",
        "Science Museum",
    ),
    "fun_things_to_do": (
        "Amusement Park",
        "Water Park",
        "Arcade",
        "Escape Room",
        "Go Kart Track",
        "Mini Golf Course",
    ),
    "romantic_scenic_places": (
        "Scenic Lookout",
        "Botanical Garden",
        "Garden",
        "Waterfront",
        "Beach",
        "Lake",
    ),
}


def _expected_ids(names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(EXPECTED_ATTRACTION_IDS_BY_NAME[name] for name in names)


class FoursquareTaxonomyTests(unittest.TestCase):
    def test_registry_contains_exactly_the_76_verified_attractions(self) -> None:
        actual = {
            category.official_name: category.provider_category_id
            for category in ATTRACTION_CATEGORIES
        }

        self.assertEqual(len(ATTRACTION_CATEGORIES), 76)
        self.assertEqual(actual, EXPECTED_ATTRACTION_IDS_BY_NAME)

    def test_provider_category_ids_are_unique(self) -> None:
        category_ids = [
            category.provider_category_id
            for category in ALL_FOURSQUARE_CATEGORIES
        ]

        self.assertEqual(len(category_ids), len(set(category_ids)))
        self.assertEqual(len(CATEGORIES_BY_ID), len(ALL_FOURSQUARE_CATEGORIES))

    def test_provider_ids_are_nonempty_bson_style_strings(self) -> None:
        for category in ALL_FOURSQUARE_CATEGORIES:
            with self.subTest(category=category.official_name):
                self.assertIsInstance(category.provider_category_id, str)
                self.assertRegex(category.provider_category_id, r"^[0-9a-f]{24}$")

    def test_no_legacy_five_digit_numeric_category_ids_exist(self) -> None:
        for category in ALL_FOURSQUARE_CATEGORIES:
            with self.subTest(category=category.official_name):
                self.assertIsNone(
                    re.fullmatch(r"\d{5}", category.provider_category_id)
                )

    def test_every_category_has_an_official_name_and_family(self) -> None:
        for category in ALL_FOURSQUARE_CATEGORIES:
            with self.subTest(category=category.provider_category_id):
                self.assertTrue(category.official_name.strip())
                self.assertIsInstance(category.family, FoursquareCategoryFamily)

    def test_every_required_attraction_family_is_used(self) -> None:
        required_families = {
            FoursquareCategoryFamily.MUSEUMS,
            FoursquareCategoryFamily.ART_AND_CULTURE,
            FoursquareCategoryFamily.HERITAGE,
            FoursquareCategoryFamily.SPIRITUAL,
            FoursquareCategoryFamily.SCENIC,
            FoursquareCategoryFamily.PARKS_AND_GARDENS,
            FoursquareCategoryFamily.NATURAL_FEATURES,
            FoursquareCategoryFamily.WILDLIFE,
            FoursquareCategoryFamily.TRAILS_AND_OUTDOORS,
            FoursquareCategoryFamily.FAMILY,
            FoursquareCategoryFamily.EDUCATIONAL,
        }

        self.assertEqual(
            {category.family for category in ATTRACTION_CATEGORIES},
            required_families,
        )

    def test_exactly_28_attraction_categories_are_generic(self) -> None:
        generic_ids = {
            category.provider_category_id
            for category in ATTRACTION_CATEGORIES
            if category.generic_discovery
        }

        self.assertEqual(len(generic_ids), 28)

    def test_generic_groups_have_exact_verified_members_and_sizes(self) -> None:
        self.assertEqual(
            tuple(GENERIC_ATTRACTION_GROUPS),
            tuple(EXPECTED_GENERIC_GROUP_NAMES),
        )

        for group_name, category_names in EXPECTED_GENERIC_GROUP_NAMES.items():
            with self.subTest(group=group_name):
                self.assertEqual(
                    GENERIC_ATTRACTION_GROUPS[group_name],
                    _expected_ids(category_names),
                )

        self.assertEqual(
            [len(group) for group in GENERIC_ATTRACTION_GROUPS.values()],
            [8, 8, 8, 4],
        )

    def test_generic_group_union_has_28_unique_registered_ids(self) -> None:
        grouped_ids = {
            category_id
            for group in GENERIC_ATTRACTION_GROUPS.values()
            for category_id in group
        }
        registered_attraction_ids = {
            category.provider_category_id for category in ATTRACTION_CATEGORIES
        }

        self.assertEqual(len(grouped_ids), 28)
        self.assertTrue(grouped_ids.issubset(registered_attraction_ids))

    def test_generic_flags_match_the_generic_group_union(self) -> None:
        grouped_ids = {
            category_id
            for group in GENERIC_ATTRACTION_GROUPS.values()
            for category_id in group
        }
        flagged_ids = {
            category.provider_category_id
            for category in ATTRACTION_CATEGORIES
            if category.generic_discovery
        }

        self.assertEqual(flagged_ids, grouped_ids)

    def test_intent_presets_have_exact_verified_registered_members(self) -> None:
        self.assertEqual(
            tuple(INTENT_CATEGORY_PRESETS),
            tuple(EXPECTED_INTENT_PRESET_NAMES),
        )

        for preset_name, category_names in EXPECTED_INTENT_PRESET_NAMES.items():
            with self.subTest(preset=preset_name):
                expected_ids = _expected_ids(category_names)
                self.assertEqual(
                    INTENT_CATEGORY_PRESETS[preset_name],
                    expected_ids,
                )
                self.assertTrue(
                    set(expected_ids).issubset(CATEGORIES_BY_ID)
                )

    def test_every_intent_preset_has_immutable_whole_token_aliases(self) -> None:
        self.assertEqual(
            tuple(ATTRACTION_INTENT_ALIASES),
            tuple(INTENT_CATEGORY_PRESETS),
        )
        self.assertEqual(
            resolve_attraction_intent_presets(
                ("Historic temples and scenic waterfalls",)
            ),
            ("temples", "historic_places", "waterfalls", "scenic_places"),
        )
        self.assertEqual(resolve_attraction_intent_presets(("parking areas",)), ())

    def test_hotel_and_restaurant_canonical_ids_are_unchanged(self) -> None:
        self.assertEqual(HOTEL_CATEGORY_ID, "4bf58dd8d48988d1fa931735")
        self.assertEqual(RESTAURANT_CATEGORY_ID, "4d4b7105d754a06374d81259")

    def test_active_attraction_ids_are_unchanged(self) -> None:
        self.assertEqual(
            ACTIVE_ATTRACTION_CATEGORY_IDS,
            (
                "4bf58dd8d48988d181941735",
                "4deefb944765f83613cdba6e",
                "4bf58dd8d48988d131941735",
            ),
        )

    def test_registry_objects_and_mappings_are_immutable(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            ATTRACTION_CATEGORIES[0].official_name = "Changed"  # type: ignore[misc]

        with self.assertRaises(TypeError):
            CATEGORIES_BY_ID["new"] = ATTRACTION_CATEGORIES[0]  # type: ignore[index]

        with self.assertRaises(TypeError):
            GENERIC_ATTRACTION_GROUPS["new"] = ()  # type: ignore[index]

        with self.assertRaises(TypeError):
            INTENT_CATEGORY_PRESETS["new"] = ()  # type: ignore[index]

        with self.assertRaises(TypeError):
            ATTRACTION_INTENT_ALIASES["new"] = ()  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
