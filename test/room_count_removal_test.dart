import 'package:flutter_test/flutter_test.dart';
import 'package:trip_logic/models/travel_context.dart';

void main() {
  test('historical room count is ignored and not serialized again', () {
    final context = TravelContext.fromJson(<String, dynamic>{
      'revision': 3,
      'travellerCount': 4,
      'roomCount': 2,
      'missingFields': <String>['roomCount', 'travelMode'],
    });

    expect(context.travellerCount, 4);
    expect(context.missingFields, <String>['travelMode']);

    final serialized = context.toJson();
    expect(serialized.containsKey('roomCount'), isFalse);
    expect(serialized['travellerCount'], 4);
    expect(serialized['missingFields'], <String>['travelMode']);
  });

  test('traveller and hotel-planning data remain independent', () {
    final context = TravelContext.fromJson(<String, dynamic>{
      'travellerCount': 2,
      'tripStartDate': '2026-09-10',
      'tripEndDate': '2026-09-12',
      'requestGroups': <Map<String, dynamic>>[
        <String, dynamic>{
          'id': 'hotel-request',
          'kind': 'hotel',
          'query': 'boutique hotels',
          'preferences': <String>['boutique hotel'],
          'required': true,
        },
      ],
    });

    expect(context.travellerCount, 2);
    expect(context.tripDurationDays, 3);
    expect(context.requestGroups.single.kind, TravelRequestKind.hotel);
    expect(context.requestGroups.single.preferences, <String>[
      'boutique hotel',
    ]);
    expect(context.toJson().containsKey('roomCount'), isFalse);
  });
}
