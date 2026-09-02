import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:trip_logic/models/recommendation_group.dart';
import 'package:trip_logic/models/travel_context.dart';
import 'package:trip_logic/widgets/recommendation_group_view.dart';

void main() {
  RecommendationGroup groupWith(List<PlaceRecommendation> recommendations) {
    return RecommendationGroup(
      requestGroupId: 'restaurant-request',
      recommendationType: TravelRequestKind.restaurant,
      required: true,
      result: RecommendationResult(
        recommendationType: TravelRequestKind.restaurant,
        count: recommendations.length,
        topRecommendations: recommendations.take(3).toList(),
        moreRecommendations: recommendations.skip(3).toList(),
      ),
    );
  }

  PlaceRecommendation place({
    String id = 'place',
    String name = 'Provider Place',
    double? rating,
    RecommendationOpeningHours? hours,
    int? distanceMeters,
    RecommendationRoute? route,
  }) {
    return PlaceRecommendation(
      id: id,
      name: name,
      categories: const <RecommendationPlaceCategory>[
        RecommendationPlaceCategory(id: 'category', name: 'Restaurant'),
      ],
      rating: rating,
      hours: hours,
      distanceMeters: distanceMeters,
      route: route,
    );
  }

  Future<void> pumpGroup(WidgetTester tester, RecommendationGroup group) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: RecommendationGroupView(group: group),
          ),
        ),
      ),
    );
  }

  testWidgets('unavailable rating hours and distance are always explicit', (
    tester,
  ) async {
    await pumpGroup(tester, groupWith(<PlaceRecommendation>[place()]));

    expect(find.text('Rating: Not available'), findsOneWidget);
    expect(find.text('Hours: Not available'), findsOneWidget);
    expect(find.text('Distance: Not available'), findsOneWidget);
  });

  testWidgets('native Foursquare rating is displayed on the ten-point scale', (
    tester,
  ) async {
    await pumpGroup(
      tester,
      groupWith(<PlaceRecommendation>[place(rating: 8.7)]),
    );

    expect(find.text('Rating: 8.7/10'), findsOneWidget);
  });

  testWidgets('provider hours display text is preferred', (tester) async {
    final hours = RecommendationOpeningHours(
      regular: const <RecommendationOpeningInterval>[],
      display: 'Mon–Sun 9:00 AM–9:00 PM',
    );

    await pumpGroup(
      tester,
      groupWith(<PlaceRecommendation>[place(hours: hours)]),
    );

    expect(find.text('Hours: Mon–Sun 9:00 AM–9:00 PM'), findsOneWidget);
  });

  testWidgets('regular hours retain multiple and overnight intervals', (
    tester,
  ) async {
    final hours = RecommendationOpeningHours(
      regular: const <RecommendationOpeningInterval>[
        RecommendationOpeningInterval(
          day: 1,
          openingTime: '09:00',
          closingTime: '12:00',
          overnight: false,
          allDay: false,
        ),
        RecommendationOpeningInterval(
          day: 1,
          openingTime: '14:00',
          closingTime: '18:00',
          overnight: false,
          allDay: false,
        ),
        RecommendationOpeningInterval(
          day: 5,
          openingTime: '18:00',
          closingTime: '02:00',
          overnight: true,
          allDay: false,
        ),
      ],
    );

    await pumpGroup(
      tester,
      groupWith(<PlaceRecommendation>[place(hours: hours)]),
    );

    expect(
      find.text(
        'Hours: Mon 09:00–12:00, 14:00–18:00; '
        'Fri 18:00–02:00 (next day)',
      ),
      findsOneWidget,
    );
  });

  testWidgets('current-open status alone is not future-hours proof', (
    tester,
  ) async {
    final hours = RecommendationOpeningHours(
      regular: const <RecommendationOpeningInterval>[],
      openNow: true,
    );

    await pumpGroup(
      tester,
      groupWith(<PlaceRecommendation>[place(hours: hours)]),
    );

    expect(find.text('Hours: Not available'), findsOneWidget);
    expect(find.textContaining('Open now'), findsNothing);
  });

  testWidgets('genuine ORS route distance has display priority', (
    tester,
  ) async {
    const route = RecommendationRoute(
      available: true,
      travelMode: 'driving',
      durationMinutes: 20,
      distanceKilometres: 8.4,
    );

    await pumpGroup(
      tester,
      groupWith(<PlaceRecommendation>[
        place(distanceMeters: 429, route: route),
      ]),
    );

    expect(find.text('Route distance: 8.4 km'), findsOneWidget);
    expect(find.textContaining('From search area'), findsNothing);
  });

  testWidgets('Foursquare distance is labelled as search-area distance', (
    tester,
  ) async {
    const route = RecommendationRoute(available: false);

    await pumpGroup(
      tester,
      groupWith(<PlaceRecommendation>[
        place(distanceMeters: 429, route: route),
        place(id: 'far', name: 'Far Place', distanceMeters: 2430, route: route),
      ]),
    );

    expect(find.text('From search area: 429 m'), findsOneWidget);
    expect(find.text('From search area: 2.4 km'), findsOneWidget);
    expect(find.textContaining('from you'), findsNothing);
  });

  testWidgets('six recommendation cards remain renderable', (tester) async {
    final recommendations = List<PlaceRecommendation>.generate(
      6,
      (index) => place(id: 'place-$index', name: 'Place $index'),
    );

    await pumpGroup(tester, groupWith(recommendations));

    for (var index = 0; index < 6; index += 1) {
      expect(find.text('Place $index'), findsOneWidget);
    }
  });
}
