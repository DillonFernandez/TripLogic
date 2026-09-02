"""Verified, immutable Foursquare provider taxonomy used by Trip Logic.

Source: Foursquare Places Open Source / Pro / Premium category taxonomy
https://docs.foursquare.com/data-products/docs/categories

Places API version: 2025-06-17
Taxonomy accessed: 2026-08-28

Only deterministic backend code may select these provider identifiers.  The
conversation recommendation adapter resolves already-structured traveller
text through the immutable generic groups and intent aliases in this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class FoursquareCategoryFamily(str, Enum):
    """Trip Logic family for a verified Foursquare category."""

    HOTEL = "hotel"
    RESTAURANT = "restaurant"
    MUSEUMS = "museums"
    ART_AND_CULTURE = "art_and_culture"
    HERITAGE = "heritage"
    SPIRITUAL = "spiritual"
    SCENIC = "scenic"
    PARKS_AND_GARDENS = "parks_and_gardens"
    NATURAL_FEATURES = "natural_features"
    WILDLIFE = "wildlife"
    TRAILS_AND_OUTDOORS = "trails_and_outdoors"
    FAMILY = "family"
    EDUCATIONAL = "educational"


@dataclass(frozen=True, slots=True)
class FoursquareCategory:
    """One verified Foursquare category and its Trip Logic classification."""

    provider_category_id: str
    official_name: str
    family: FoursquareCategoryFamily
    generic_discovery: bool = False
    parent_name: str | None = None


HOTEL_CATEGORY = FoursquareCategory(
    provider_category_id="4bf58dd8d48988d1fa931735",
    official_name="Hotel",
    family=FoursquareCategoryFamily.HOTEL,
    parent_name="Lodging",
)

RESTAURANT_CATEGORY = FoursquareCategory(
    provider_category_id="4d4b7105d754a06374d81259",
    official_name="Restaurant",
    family=FoursquareCategoryFamily.RESTAURANT,
    parent_name="Dining and Drinking",
)


ATTRACTION_CATEGORIES: tuple[FoursquareCategory, ...] = (
    # Museums
    FoursquareCategory(
        "4bf58dd8d48988d181941735",
        "Museum",
        FoursquareCategoryFamily.MUSEUMS,
        generic_discovery=True,
        parent_name="Arts and Entertainment",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d18f941735",
        "Art Museum",
        FoursquareCategoryFamily.MUSEUMS,
        parent_name="Museum",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d190941735",
        "History Museum",
        FoursquareCategoryFamily.MUSEUMS,
        parent_name="Museum",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d191941735",
        "Science Museum",
        FoursquareCategoryFamily.MUSEUMS,
        parent_name="Museum",
    ),
    # Art and culture
    FoursquareCategory(
        "4bf58dd8d48988d1e2931735",
        "Art Gallery",
        FoursquareCategoryFamily.ART_AND_CULTURE,
        generic_discovery=True,
        parent_name="Arts and Entertainment",
    ),
    FoursquareCategory(
        "52e81612bcbc57f1066b7a32",
        "Cultural Center",
        FoursquareCategoryFamily.ART_AND_CULTURE,
        generic_discovery=True,
        parent_name="Community and Government",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d1f2931735",
        "Performing Arts Venue",
        FoursquareCategoryFamily.ART_AND_CULTURE,
        parent_name="Arts and Entertainment",
    ),
    FoursquareCategory(
        "56aa371be4b08b9a8d5734db",
        "Amphitheater",
        FoursquareCategoryFamily.ART_AND_CULTURE,
        parent_name="Performing Arts Venue",
    ),
    FoursquareCategory(
        "5032792091d4c4b30a586d5c",
        "Concert Hall",
        FoursquareCategoryFamily.ART_AND_CULTURE,
        parent_name="Performing Arts Venue",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d136941735",
        "Opera House",
        FoursquareCategoryFamily.ART_AND_CULTURE,
        parent_name="Performing Arts Venue",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d137941735",
        "Theater",
        FoursquareCategoryFamily.ART_AND_CULTURE,
        parent_name="Performing Arts Venue",
    ),
    FoursquareCategory(
        "56aa371be4b08b9a8d573532",
        "Exhibit",
        FoursquareCategoryFamily.ART_AND_CULTURE,
        parent_name="Arts and Entertainment",
    ),
    FoursquareCategory(
        "507c8c4091d498d9fc8c67a9",
        "Public Art",
        FoursquareCategoryFamily.ART_AND_CULTURE,
        generic_discovery=True,
        parent_name="Arts and Entertainment",
    ),
    FoursquareCategory(
        "52e81612bcbc57f1066b79ed",
        "Outdoor Sculpture",
        FoursquareCategoryFamily.ART_AND_CULTURE,
        parent_name="Public Art",
    ),
    FoursquareCategory(
        "52e81612bcbc57f1066b79ee",
        "Street Art",
        FoursquareCategoryFamily.ART_AND_CULTURE,
        parent_name="Public Art",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d166941735",
        "Sculpture Garden",
        FoursquareCategoryFamily.ART_AND_CULTURE,
        parent_name="Landmarks and Outdoors",
    ),
    # Heritage and landmarks
    FoursquareCategory(
        "4deefb944765f83613cdba6e",
        "Historic and Protected Site",
        FoursquareCategoryFamily.HERITAGE,
        generic_discovery=True,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d12d941735",
        "Monument",
        FoursquareCategoryFamily.HERITAGE,
        generic_discovery=True,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "5642206c498e4bfca532186c",
        "Memorial Site",
        FoursquareCategoryFamily.HERITAGE,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "52e81612bcbc57f1066b7a14",
        "Palace",
        FoursquareCategoryFamily.HERITAGE,
        generic_discovery=True,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "50aaa49e4b90af0d42d5de11",
        "Castle",
        FoursquareCategoryFamily.HERITAGE,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d15d941735",
        "Lighthouse",
        FoursquareCategoryFamily.HERITAGE,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d1df941735",
        "Bridge",
        FoursquareCategoryFamily.HERITAGE,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "56aa371be4b08b9a8d573547",
        "Fountain",
        FoursquareCategoryFamily.HERITAGE,
        parent_name="Landmarks and Outdoors",
    ),
    # Spiritual places
    FoursquareCategory(
        "4bf58dd8d48988d131941735",
        "Spiritual Center",
        FoursquareCategoryFamily.SPIRITUAL,
        generic_discovery=True,
        parent_name="Community and Government",
    ),
    FoursquareCategory(
        "52e81612bcbc57f1066b7a3e",
        "Buddhist Temple",
        FoursquareCategoryFamily.SPIRITUAL,
        parent_name="Spiritual Center",
    ),
    FoursquareCategory(
        "52e81612bcbc57f1066b7a3f",
        "Hindu Temple",
        FoursquareCategoryFamily.SPIRITUAL,
        parent_name="Spiritual Center",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d132941735",
        "Church",
        FoursquareCategoryFamily.SPIRITUAL,
        parent_name="Spiritual Center",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d138941735",
        "Mosque",
        FoursquareCategoryFamily.SPIRITUAL,
        parent_name="Spiritual Center",
    ),
    FoursquareCategory(
        "4eb1d80a4b900d56c88a45ff",
        "Shrine",
        FoursquareCategoryFamily.SPIRITUAL,
        parent_name="Spiritual Center",
    ),
    FoursquareCategory(
        "52e81612bcbc57f1066b7a40",
        "Monastery",
        FoursquareCategoryFamily.SPIRITUAL,
        parent_name="Spiritual Center",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d13a941735",
        "Temple",
        FoursquareCategoryFamily.SPIRITUAL,
        parent_name="Spiritual Center",
    ),
    FoursquareCategory(
        "56aa371be4b08b9a8d5734fc",
        "Confucian Temple",
        FoursquareCategoryFamily.SPIRITUAL,
        parent_name="Spiritual Center",
    ),
    FoursquareCategory(
        "5bae9231bedf3950379f89c9",
        "Sikh Temple",
        FoursquareCategoryFamily.SPIRITUAL,
        parent_name="Spiritual Center",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d139941735",
        "Synagogue",
        FoursquareCategoryFamily.SPIRITUAL,
        parent_name="Spiritual Center",
    ),
    # Scenic places. Mountain is classified as a natural feature below.
    FoursquareCategory(
        "4bf58dd8d48988d165941735",
        "Scenic Lookout",
        FoursquareCategoryFamily.SCENIC,
        generic_discovery=True,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "5bae9231bedf3950379f89cd",
        "Hill",
        FoursquareCategoryFamily.SCENIC,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "56aa371be4b08b9a8d5734c3",
        "Waterfront",
        FoursquareCategoryFamily.SCENIC,
        generic_discovery=True,
        parent_name="Landmarks and Outdoors",
    ),
    # Parks and gardens
    FoursquareCategory(
        "52e81612bcbc57f1066b7a22",
        "Botanical Garden",
        FoursquareCategoryFamily.PARKS_AND_GARDENS,
        generic_discovery=True,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d15a941735",
        "Garden",
        FoursquareCategoryFamily.PARKS_AND_GARDENS,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d163941735",
        "Park",
        FoursquareCategoryFamily.PARKS_AND_GARDENS,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "52e81612bcbc57f1066b7a21",
        "National Park",
        FoursquareCategoryFamily.PARKS_AND_GARDENS,
        generic_discovery=True,
        parent_name="Park",
    ),
    FoursquareCategory(
        "63be6904847c3692a84b9be0",
        "Natural Park",
        FoursquareCategoryFamily.PARKS_AND_GARDENS,
        generic_discovery=True,
        parent_name="Park",
    ),
    FoursquareCategory(
        "5bae9231bedf3950379f89d0",
        "State or Provincial Park",
        FoursquareCategoryFamily.PARKS_AND_GARDENS,
        parent_name="Park",
    ),
    FoursquareCategory(
        "63be6904847c3692a84b9be1",
        "Urban Park",
        FoursquareCategoryFamily.PARKS_AND_GARDENS,
        parent_name="Park",
    ),
    # Natural features
    FoursquareCategory(
        "4eb1d4d54b900d56c88a45fc",
        "Mountain",
        FoursquareCategoryFamily.NATURAL_FEATURES,
        generic_discovery=True,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "56aa371be4b08b9a8d573560",
        "Waterfall",
        FoursquareCategoryFamily.NATURAL_FEATURES,
        generic_discovery=True,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d1e2941735",
        "Beach",
        FoursquareCategoryFamily.NATURAL_FEATURES,
        generic_discovery=True,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d161941735",
        "Lake",
        FoursquareCategoryFamily.NATURAL_FEATURES,
        generic_discovery=True,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "4eb1d4dd4b900d56c88a45fd",
        "River",
        FoursquareCategoryFamily.NATURAL_FEATURES,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "56aa371be4b08b9a8d573511",
        "Cave",
        FoursquareCategoryFamily.NATURAL_FEATURES,
        generic_discovery=True,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "52e81612bcbc57f1066b7a23",
        "Forest",
        FoursquareCategoryFamily.NATURAL_FEATURES,
        generic_discovery=True,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "50aaa4314b90af0d42d5de10",
        "Island",
        FoursquareCategoryFamily.NATURAL_FEATURES,
        generic_discovery=True,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d160941735",
        "Hot Spring",
        FoursquareCategoryFamily.NATURAL_FEATURES,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "56aa371be4b08b9a8d573544",
        "Bay",
        FoursquareCategoryFamily.NATURAL_FEATURES,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "56aa371be4b08b9a8d573541",
        "Reservoir",
        FoursquareCategoryFamily.NATURAL_FEATURES,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "5fac018b99ce226e27fe7573",
        "Dam",
        FoursquareCategoryFamily.NATURAL_FEATURES,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d1e0941735",
        "Harbor or Marina",
        FoursquareCategoryFamily.NATURAL_FEATURES,
        parent_name="Landmarks and Outdoors",
    ),
    # Wildlife. Nature Preserve is grouped here because it is the closest
    # verified provider category for wildlife reserves and sanctuaries.
    FoursquareCategory(
        "52e81612bcbc57f1066b7a13",
        "Nature Preserve",
        FoursquareCategoryFamily.WILDLIFE,
        generic_discovery=True,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d17b941735",
        "Zoo",
        FoursquareCategoryFamily.WILDLIFE,
        generic_discovery=True,
        parent_name="Arts and Entertainment",
    ),
    FoursquareCategory(
        "4fceea171983d5d06c3e9823",
        "Aquarium",
        FoursquareCategoryFamily.WILDLIFE,
        generic_discovery=True,
        parent_name="Arts and Entertainment",
    ),
    # Trails and outdoor visitor activities
    FoursquareCategory(
        "4bf58dd8d48988d159941735",
        "Hiking Trail",
        FoursquareCategoryFamily.TRAILS_AND_OUTDOORS,
        generic_discovery=True,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "56aa371be4b08b9a8d57355e",
        "Bike Trail",
        FoursquareCategoryFamily.TRAILS_AND_OUTDOORS,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "52e81612bcbc57f1066b7a12",
        "Dive Spot",
        FoursquareCategoryFamily.TRAILS_AND_OUTDOORS,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d1e3941735",
        "Surf Spot",
        FoursquareCategoryFamily.TRAILS_AND_OUTDOORS,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "50328a4b91d4c4b30a586d6b",
        "Rock Climbing Spot",
        FoursquareCategoryFamily.TRAILS_AND_OUTDOORS,
        parent_name="Landmarks and Outdoors",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d1e4941735",
        "Campground",
        FoursquareCategoryFamily.TRAILS_AND_OUTDOORS,
        parent_name="Landmarks and Outdoors",
    ),
    # Family attractions and activities
    FoursquareCategory(
        "4bf58dd8d48988d182941735",
        "Amusement Park",
        FoursquareCategoryFamily.FAMILY,
        generic_discovery=True,
        parent_name="Arts and Entertainment",
    ),
    FoursquareCategory(
        "5109983191d435c0d71c2bb1",
        "Attraction",
        FoursquareCategoryFamily.FAMILY,
        parent_name="Amusement Park",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d193941735",
        "Water Park",
        FoursquareCategoryFamily.FAMILY,
        generic_discovery=True,
        parent_name="Arts and Entertainment",
    ),
    FoursquareCategory(
        "4bf58dd8d48988d1e1931735",
        "Arcade",
        FoursquareCategoryFamily.FAMILY,
        parent_name="Arts and Entertainment",
    ),
    FoursquareCategory(
        "5f2c2834b6d05514c704451e",
        "Escape Room",
        FoursquareCategoryFamily.FAMILY,
        parent_name="Arts and Entertainment",
    ),
    FoursquareCategory(
        "52e81612bcbc57f1066b79ea",
        "Go Kart Track",
        FoursquareCategoryFamily.FAMILY,
        parent_name="Arts and Entertainment",
    ),
    FoursquareCategory(
        "52e81612bcbc57f1066b79eb",
        "Mini Golf Course",
        FoursquareCategoryFamily.FAMILY,
        parent_name="Arts and Entertainment",
    ),
    # Educational visitor attractions
    FoursquareCategory(
        "4bf58dd8d48988d192941735",
        "Planetarium",
        FoursquareCategoryFamily.EDUCATIONAL,
        generic_discovery=True,
        parent_name="Arts and Entertainment",
    ),
    FoursquareCategory(
        "5744ccdfe4b0c0459246b4d9",
        "Observatory",
        FoursquareCategoryFamily.EDUCATIONAL,
        generic_discovery=True,
        parent_name="Community and Government",
    ),
)


ALL_FOURSQUARE_CATEGORIES: tuple[FoursquareCategory, ...] = (
    HOTEL_CATEGORY,
    RESTAURANT_CATEGORY,
    *ATTRACTION_CATEGORIES,
)

CATEGORIES_BY_ID: Mapping[str, FoursquareCategory] = MappingProxyType(
    {
        category.provider_category_id: category
        for category in ALL_FOURSQUARE_CATEGORIES
    }
)

CATEGORIES_BY_OFFICIAL_NAME: Mapping[str, FoursquareCategory] = MappingProxyType(
    {category.official_name: category for category in ALL_FOURSQUARE_CATEGORIES}
)

if len(CATEGORIES_BY_ID) != len(ALL_FOURSQUARE_CATEGORIES):
    raise RuntimeError("Foursquare provider category IDs must be unique.")

if len(CATEGORIES_BY_OFFICIAL_NAME) != len(ALL_FOURSQUARE_CATEGORIES):
    raise RuntimeError("Foursquare official category names must be unique.")


def _category_ids(*official_names: str) -> tuple[str, ...]:
    return tuple(
        CATEGORIES_BY_OFFICIAL_NAME[name].provider_category_id
        for name in official_names
    )


HOTEL_CATEGORY_ID = HOTEL_CATEGORY.provider_category_id
RESTAURANT_CATEGORY_ID = RESTAURANT_CATEGORY.provider_category_id

ACTIVE_ATTRACTION_CATEGORY_IDS = _category_ids(
    "Museum",
    "Historic and Protected Site",
    "Spiritual Center",
)


GENERIC_ATTRACTION_GROUPS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "heritage_and_culture": _category_ids(
            "Museum",
            "Art Gallery",
            "Cultural Center",
            "Public Art",
            "Historic and Protected Site",
            "Monument",
            "Palace",
            "Spiritual Center",
        ),
        "landscapes_and_water": _category_ids(
            "Scenic Lookout",
            "Waterfall",
            "Beach",
            "Mountain",
            "Cave",
            "Lake",
            "Forest",
            "Waterfront",
        ),
        "parks_wildlife_and_outdoors": _category_ids(
            "Botanical Garden",
            "National Park",
            "Natural Park",
            "Nature Preserve",
            "Hiking Trail",
            "Zoo",
            "Aquarium",
            "Island",
        ),
        "family_and_learning": _category_ids(
            "Amusement Park",
            "Water Park",
            "Planetarium",
            "Observatory",
        ),
    }
)


INTENT_CATEGORY_PRESETS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "temples": _category_ids(
            "Buddhist Temple",
            "Hindu Temple",
            "Temple",
            "Shrine",
            "Monastery",
        ),
        "historic_places": _category_ids(
            "Historic and Protected Site",
            "Monument",
            "Memorial Site",
            "Palace",
            "Castle",
            "Lighthouse",
        ),
        "museums": _category_ids("Museum"),
        "art_galleries": _category_ids("Art Gallery"),
        "waterfalls": _category_ids("Waterfall"),
        "beaches": _category_ids("Beach"),
        "wildlife": _category_ids(
            "Nature Preserve",
            "National Park",
            "Natural Park",
            "Zoo",
            "Aquarium",
        ),
        "nature": _category_ids(
            "Nature Preserve",
            "National Park",
            "Natural Park",
            "Forest",
            "Mountain",
            "Waterfall",
            "Lake",
            "Cave",
        ),
        "scenic_places": _category_ids(
            "Scenic Lookout",
            "Mountain",
            "Hill",
            "Waterfall",
            "Waterfront",
        ),
        "parks": _category_ids(
            "National Park",
            "Natural Park",
            "State or Provincial Park",
            "Urban Park",
        ),
        "botanical_gardens": _category_ids("Botanical Garden"),
        "hiking": _category_ids(
            "Hiking Trail",
            "Mountain",
            "Nature Preserve",
        ),
        "family_attractions": _category_ids(
            "Amusement Park",
            "Water Park",
            "Zoo",
            "Aquarium",
            "Planetarium",
            "Science Museum",
        ),
        "fun_things_to_do": _category_ids(
            "Amusement Park",
            "Water Park",
            "Arcade",
            "Escape Room",
            "Go Kart Track",
            "Mini Golf Course",
        ),
        "romantic_scenic_places": _category_ids(
            "Scenic Lookout",
            "Botanical Garden",
            "Garden",
            "Waterfront",
            "Beach",
            "Lake",
        ),
    }
)


ATTRACTION_INTENT_ALIASES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "temples": (
            "temple",
            "temples",
            "buddhist temple",
            "buddhist temples",
            "hindu temple",
            "hindu temples",
            "shrine",
            "shrines",
            "monastery",
            "monasteries",
        ),
        "historic_places": (
            "historic",
            "historical",
            "heritage",
            "historic place",
            "historic places",
            "historical place",
            "historical places",
            "historic site",
            "historic sites",
            "historical site",
            "historical sites",
            "monument",
            "monuments",
            "palace",
            "palaces",
            "castle",
            "castles",
            "lighthouse",
            "lighthouses",
        ),
        "museums": (
            "museum",
            "museums",
        ),
        "art_galleries": (
            "art gallery",
            "art galleries",
        ),
        "waterfalls": (
            "waterfall",
            "waterfalls",
        ),
        "beaches": (
            "beach",
            "beaches",
        ),
        "wildlife": (
            "wildlife",
            "wild life",
            "wildlife reserve",
            "wildlife reserves",
            "zoo",
            "zoos",
            "aquarium",
            "aquariums",
            "safari",
            "safaris",
        ),
        "nature": (
            "nature",
            "natural attraction",
            "natural attractions",
            "natural place",
            "natural places",
            "forest",
            "forests",
            "mountain",
            "mountains",
            "cave",
            "caves",
            "lake",
            "lakes",
        ),
        "scenic_places": (
            "scenic",
            "scenic place",
            "scenic places",
            "scenic lookout",
            "scenic lookouts",
            "viewpoint",
            "viewpoints",
            "view point",
            "view points",
        ),
        "parks": (
            "park",
            "parks",
            "national park",
            "national parks",
            "natural park",
            "natural parks",
            "urban park",
            "urban parks",
        ),
        "botanical_gardens": (
            "botanical garden",
            "botanical gardens",
            "botanic garden",
            "botanic gardens",
        ),
        "hiking": (
            "hiking",
            "hike",
            "hikes",
            "hiking trail",
            "hiking trails",
            "trek",
            "treks",
            "trekking",
        ),
        "family_attractions": (
            "family attraction",
            "family attractions",
            "family friendly",
            "kid friendly",
            "kids attractions",
            "children attractions",
        ),
        "fun_things_to_do": (
            "fun things to do",
            "fun activities",
            "amusement park",
            "amusement parks",
            "water park",
            "water parks",
            "arcade",
            "arcades",
            "escape room",
            "escape rooms",
            "go kart",
            "go karts",
            "mini golf",
        ),
        "romantic_scenic_places": (
            "romantic scenic place",
            "romantic scenic places",
            "romantic place",
            "romantic places",
            "romantic view",
            "romantic views",
            "romantic getaway",
            "romantic getaways",
        ),
    }
)


GENERIC_ATTRACTION_SIGNAL_ALIASES: tuple[str, ...] = (
    "surprise me",
    "choose for me",
    "pick for me",
    "anything",
    "anything is fine",
    "anything is okay",
    "anything is ok",
    "no preference",
    "no preferences",
    "no specific preference",
    "i have no clue",
    "i dont have a clue",
    "no clue",
    "first time here",
    "first time visitor",
    "first time in sri lanka",
    "whatever you recommend",
    "i dont mind",
    "i do not mind",
)


if set(ATTRACTION_INTENT_ALIASES) != set(INTENT_CATEGORY_PRESETS):
    raise RuntimeError("Every attraction intent preset must define aliases.")


def normalize_attraction_intent_text(value: str) -> str:
    """Normalize semantic text for deterministic whole-token matching."""

    normalized = value.casefold().replace("’", "'").replace("“", '"')
    normalized = normalized.replace("”", '"').replace("—", " ").replace("–", " ")
    normalized = normalized.replace("'", "")
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _contains_normalized_phrase(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} "


def resolve_attraction_intent_presets(values: tuple[str, ...]) -> tuple[str, ...]:
    """Resolve verified preset keys from already-extracted semantic text."""

    normalized_values = tuple(
        normalized
        for value in values
        if (normalized := normalize_attraction_intent_text(value))
    )

    matched_presets = [
        preset_name
        for preset_name, aliases in ATTRACTION_INTENT_ALIASES.items()
        if any(
            _contains_normalized_phrase(normalized_value, alias)
            for normalized_value in normalized_values
            for alias in aliases
        )
    ]

    # The romantic preset is intentionally more specific than the nested
    # scenic wording and already contains the appropriate scenic categories.
    if (
        "romantic_scenic_places" in matched_presets
        and "scenic_places" in matched_presets
    ):
        matched_presets.remove("scenic_places")

    return tuple(matched_presets)


def strip_generic_attraction_signals(value: str) -> str:
    """Remove known no-preference wording without substring matching."""

    tokens = normalize_attraction_intent_text(value).split()

    for alias in sorted(
        GENERIC_ATTRACTION_SIGNAL_ALIASES,
        key=lambda item: len(item.split()),
        reverse=True,
    ):
        alias_tokens = alias.split()
        alias_length = len(alias_tokens)
        index = 0

        while index <= len(tokens) - alias_length:
            if tokens[index : index + alias_length] == alias_tokens:
                del tokens[index : index + alias_length]
                continue

            index += 1

    return " ".join(tokens)
