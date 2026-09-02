import 'package:flutter_test/flutter_test.dart';
import 'package:trip_logic/models/recommendation_group.dart';

void main() {
  Map<String, dynamic> placeJson({
    dynamic rating,
    dynamic hours,
    dynamic distanceMeters = 429,
  }) {
    return <String, dynamic>{
      'id': 'provider-place',
      'name': 'Provider Place',
      'categories': <Map<String, dynamic>>[
        <String, dynamic>{'id': 'category', 'name': 'Restaurant'},
      ],
      'distanceMeters': distanceMeters,
      'rating': rating,
      'hours': hours,
    };
  }

  test('null rating and hours remain unavailable', () {
    final place = PlaceRecommendation.fromJson(placeJson());

    expect(place.rating, isNull);
    expect(place.hours, isNull);
    expect(place.distanceMeters, 429);
  });

  test('integer and double ratings parse on the native zero-to-ten scale', () {
    expect(PlaceRecommendation.fromJson(placeJson(rating: 8)).rating, 8.0);
    expect(PlaceRecommendation.fromJson(placeJson(rating: 8.7)).rating, 8.7);
  });

  test('malformed or out-of-range ratings do not crash or become zero', () {
    for (final rating in <dynamic>[
      '8.7',
      true,
      <String, dynamic>{},
      -0.1,
      10.1,
    ]) {
      expect(
        PlaceRecommendation.fromJson(placeJson(rating: rating)).rating,
        isNull,
      );
    }
  });

  test('structured hours and multiple intervals are preserved', () {
    final place = PlaceRecommendation.fromJson(
      placeJson(
        hours: <String, dynamic>{
          'regular': <Map<String, dynamic>>[
            <String, dynamic>{
              'day': 1,
              'openingTime': '09:00',
              'closingTime': '12:00',
              'overnight': false,
              'allDay': false,
            },
            <String, dynamic>{
              'day': 1,
              'openingTime': '14:00',
              'closingTime': '18:00',
              'overnight': false,
              'allDay': false,
            },
          ],
          'openNow': true,
          'isLocalHoliday': false,
          'display': 'Mon 9:00 AM–6:00 PM',
        },
      ),
    );

    expect(place.hours, isNotNull);
    expect(place.hours!.regular, hasLength(2));
    expect(place.hours!.openNow, isTrue);
    expect(place.hours!.isLocalHoliday, isFalse);
    expect(place.hours!.display, 'Mon 9:00 AM–6:00 PM');
  });

  test('overnight and all-day flags are retained', () {
    final place = PlaceRecommendation.fromJson(
      placeJson(
        hours: <String, dynamic>{
          'regular': <Map<String, dynamic>>[
            <String, dynamic>{
              'day': 5,
              'openingTime': '18:00',
              'closingTime': '02:00',
              'overnight': true,
              'allDay': false,
            },
            <String, dynamic>{
              'day': 7,
              'openingTime': '00:00',
              'closingTime': '24:00',
              'overnight': false,
              'allDay': true,
            },
          ],
        },
      ),
    );

    expect(place.hours!.regular.first.overnight, isTrue);
    expect(place.hours!.regular.last.allDay, isTrue);
  });

  test('malformed optional hours pieces are ignored safely', () {
    final place = PlaceRecommendation.fromJson(
      placeJson(
        hours: <String, dynamic>{
          'regular': <dynamic>[
            <String, dynamic>{
              'day': 8,
              'openingTime': 'bad',
              'closingTime': '17:00',
            },
            'malformed',
          ],
          'openNow': 'yes',
          'isLocalHoliday': 1,
          'display': <String, dynamic>{},
        },
      ),
    );

    expect(place.hours, isNull);
  });

  test('malformed distance does not crash or fabricate a value', () {
    expect(
      PlaceRecommendation.fromJson(
        placeJson(distanceMeters: '429'),
      ).distanceMeters,
      isNull,
    );
  });
}
