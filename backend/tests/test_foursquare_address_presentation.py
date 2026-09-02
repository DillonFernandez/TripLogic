"""Focused contracts for conservative Foursquare address presentation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import foursquare  # noqa: E402


class FoursquareAddressPresentationTests(unittest.TestCase):
    @staticmethod
    def _raw_place(location: Any) -> dict[str, Any]:
        return {
            "fsq_place_id": "provider-place",
            "name": "The Empire Café",
            "categories": [],
            "location": location,
            "latitude": 7.29347,
            "longitude": 80.63892,
            "distance": 429,
        }

    def test_valid_formatted_address_is_preferred(self) -> None:
        place = foursquare._normalize_place(
            self._raw_place(
                {
                    "address": "Temple Street",
                    "locality": "Kandy",
                    "region": "Himāchal Pradesh",
                    "country": "LK",
                    "formatted_address": "  Temple Street, Kandy  ",
                }
            )
        )

        self.assertIsNotNone(place)
        assert place is not None
        self.assertEqual(place["location"]["displayAddress"], "Temple Street, Kandy")

    def test_empty_or_malformed_formatted_address_uses_safe_fallback(self) -> None:
        for formatted_address in (None, "   ", {}, []):
            with self.subTest(formatted_address=formatted_address):
                place = foursquare._normalize_place(
                    self._raw_place(
                        {
                            "address": "Temple Street",
                            "locality": "Kandy",
                            "region": "Himāchal Pradesh",
                            "country": "LK",
                            "formatted_address": formatted_address,
                        }
                    )
                )

                self.assertIsNotNone(place)
                assert place is not None
                self.assertEqual(
                    place["location"]["displayAddress"],
                    "Temple Street, Kandy, Sri Lanka",
                )

    def test_contradictory_region_is_not_appended_to_display_address(self) -> None:
        place = foursquare._normalize_place(
            self._raw_place(
                {
                    "address": "Temple Street",
                    "locality": "Kandy",
                    "region": "Himāchal Pradesh",
                    "country": "LK",
                }
            )
        )

        self.assertIsNotNone(place)
        assert place is not None
        self.assertEqual(place["location"]["region"], "Himāchal Pradesh")
        self.assertNotIn(
            "Himāchal Pradesh",
            place["location"]["displayAddress"],
        )

    def test_provider_locality_is_retained(self) -> None:
        location = foursquare._normalize_location(
            {
                "locality": "Kandy",
                "country": "LK",
            }
        )

        self.assertEqual(location["locality"], "Kandy")
        self.assertEqual(location["displayAddress"], "Kandy, Sri Lanka")

    def test_country_is_not_duplicated(self) -> None:
        location = foursquare._normalize_location(
            {
                "address": "Temple Street, Kandy, Sri Lanka",
                "locality": "Kandy",
                "country": "LK",
            }
        )

        self.assertEqual(
            location["displayAddress"],
            "Temple Street, Kandy, Sri Lanka",
        )
        self.assertEqual(location["displayAddress"].count("Sri Lanka"), 1)

    def test_missing_address_does_not_reject_an_in_scope_place(self) -> None:
        place = foursquare._normalize_place(
            self._raw_place(
                {
                    "locality": "Kandy",
                    "country": "LK",
                }
            )
        )

        self.assertIsNotNone(place)
        assert place is not None
        self.assertIsNone(place["location"]["address"])
        self.assertEqual(place["location"]["displayAddress"], "Kandy, Sri Lanka")

    def test_existing_locality_conflict_contract_is_unchanged(self) -> None:
        self.assertFalse(
            foursquare._has_conflicting_locality(
                {
                    "locality": "Kandy",
                    "region": "Himāchal Pradesh",
                },
                expected_locality="Kandy",
            )
        )
        self.assertTrue(
            foursquare._has_conflicting_locality(
                {"locality": "Galle"},
                expected_locality="Kandy",
            )
        )


if __name__ == "__main__":
    unittest.main()
