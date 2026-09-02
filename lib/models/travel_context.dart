enum TravelContextStage {
  collecting,
  awaitingConfirmation,
  confirmed,
  recommending,
  awaitingSelection,
  planning,
  completed,
}

enum TravelRequestKind { attraction, hotel, restaurant, unknown }

enum TravellerType {
  soloTraveller,
  couple,
  family,
  friendsGroup,
  seniorTravellers,
  unknown,
}

enum TravelLocationSource { current, searched, fixedPlace, unknown }

enum FixedTravelPlaceRole {
  dailyBase,
  requiredStop,
  startPoint,
  endPoint,
  overnightStop,
}

class TravelLocation {
  const TravelLocation({
    required this.displayName,
    required this.source,
    this.latitude,
    this.longitude,
    this.providerPlaceId,
    this.verified = false,
  });

  static const Object _unset = Object();

  factory TravelLocation.fromJson(Map<String, dynamic> json) {
    return TravelLocation(
      displayName: _stringValue(json['displayName']) ?? '',
      source:
          _enumByName(
            TravelLocationSource.values,
            _stringValue(json['source']),
          ) ??
          TravelLocationSource.unknown,
      latitude: _doubleValue(json['latitude']),
      longitude: _doubleValue(json['longitude']),
      providerPlaceId: _stringValue(json['providerPlaceId']),
      verified: json['verified'] == true,
    );
  }

  final String displayName;
  final TravelLocationSource source;
  final double? latitude;
  final double? longitude;
  final String? providerPlaceId;
  final bool verified;

  bool get hasCoordinates {
    return latitude != null && longitude != null;
  }

  bool get hasPartialCoordinates {
    return (latitude == null) != (longitude == null);
  }

  bool get hasValidCoordinates {
    final selectedLatitude = latitude;
    final selectedLongitude = longitude;

    if (selectedLatitude == null || selectedLongitude == null) {
      return false;
    }

    return selectedLatitude.isFinite &&
        selectedLatitude >= -90 &&
        selectedLatitude <= 90 &&
        selectedLongitude.isFinite &&
        selectedLongitude >= -180 &&
        selectedLongitude <= 180;
  }

  bool get isValid {
    final normalizedDisplayName = displayName.trim();

    return normalizedDisplayName.length >= 2 &&
        normalizedDisplayName.length <= 150 &&
        !hasPartialCoordinates &&
        (!hasCoordinates || hasValidCoordinates);
  }

  bool get isRouteReady {
    return isValid && verified && hasValidCoordinates;
  }

  Map<String, dynamic> toJson() {
    return {
      'displayName': displayName.trim(),
      'source': source.name,
      'latitude': latitude,
      'longitude': longitude,
      'providerPlaceId': providerPlaceId,
      'verified': verified,
    };
  }

  TravelLocation copyWith({
    String? displayName,
    TravelLocationSource? source,
    Object? latitude = _unset,
    Object? longitude = _unset,
    Object? providerPlaceId = _unset,
    bool? verified,
  }) {
    return TravelLocation(
      displayName: displayName ?? this.displayName,
      source: source ?? this.source,
      latitude: identical(latitude, _unset)
          ? this.latitude
          : latitude as double?,
      longitude: identical(longitude, _unset)
          ? this.longitude
          : longitude as double?,
      providerPlaceId: identical(providerPlaceId, _unset)
          ? this.providerPlaceId
          : providerPlaceId as String?,
      verified: verified ?? this.verified,
    );
  }
}

class TravelRequestGroup {
  TravelRequestGroup({
    required this.id,
    required this.kind,
    required this.query,
    List<String> preferences = const <String>[],
    this.requestedCount,
    this.required = true,
    List<String> selectedPlaceIds = const <String>[],
  }) : preferences = List<String>.unmodifiable(_normalizedStrings(preferences)),
       selectedPlaceIds = List<String>.unmodifiable(
         _normalizedStrings(selectedPlaceIds),
       );

  factory TravelRequestGroup.fromJson(Map<String, dynamic> json) {
    return TravelRequestGroup(
      id: _stringValue(json['id']) ?? '',
      kind:
          _enumByName(TravelRequestKind.values, _stringValue(json['kind'])) ??
          TravelRequestKind.unknown,
      query: _stringValue(json['query']) ?? '',
      preferences: _stringList(json['preferences']),
      requestedCount: _integerValue(json['requestedCount']),
      required: json['required'] != false,
      selectedPlaceIds: _stringList(json['selectedPlaceIds']),
    );
  }

  final String id;
  final TravelRequestKind kind;

  /// Keeps the traveller's intended request, such as "local seafood"
  /// or "family-friendly museums".
  final String query;

  final List<String> preferences;

  /// Null means the traveller did not set a strict number.
  final int? requestedCount;

  final bool required;
  final List<String> selectedPlaceIds;

  bool get isValid {
    return id.trim().isNotEmpty &&
        !id.contains('/') &&
        kind != TravelRequestKind.unknown &&
        query.trim().isNotEmpty &&
        (requestedCount == null || requestedCount! > 0);
  }

  bool get hasSelections {
    return selectedPlaceIds.isNotEmpty;
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id.trim(),
      'kind': kind.name,
      'query': query.trim(),
      'preferences': preferences,
      'requestedCount': requestedCount,
      'required': required,
      'selectedPlaceIds': selectedPlaceIds,
    };
  }

  TravelRequestGroup copyWith({
    String? id,
    TravelRequestKind? kind,
    String? query,
    List<String>? preferences,
    Object? requestedCount = _unset,
    bool? required,
    List<String>? selectedPlaceIds,
  }) {
    return TravelRequestGroup(
      id: id ?? this.id,
      kind: kind ?? this.kind,
      query: query ?? this.query,
      preferences: preferences ?? this.preferences,
      requestedCount: identical(requestedCount, _unset)
          ? this.requestedCount
          : requestedCount as int?,
      required: required ?? this.required,
      selectedPlaceIds: selectedPlaceIds ?? this.selectedPlaceIds,
    );
  }

  static const Object _unset = Object();
}

class FixedTravelPlace {
  const FixedTravelPlace({
    required this.id,
    required this.name,
    required this.role,
    required this.location,
    this.notes,
    this.confirmed = true,
  });

  static const Object _unset = Object();

  factory FixedTravelPlace.fromJson(Map<String, dynamic> json) {
    return FixedTravelPlace(
      id: _stringValue(json['id']) ?? '',
      name: _stringValue(json['name']) ?? '',
      role:
          _enumByName(
            FixedTravelPlaceRole.values,
            _stringValue(json['role']),
          ) ??
          FixedTravelPlaceRole.requiredStop,
      location: TravelLocation.fromJson(
        _mapValue(json['location']) ?? const <String, dynamic>{},
      ),
      notes: _stringValue(json['notes']),
      confirmed: json['confirmed'] != false,
    );
  }

  final String id;
  final String name;
  final FixedTravelPlaceRole role;
  final TravelLocation location;
  final String? notes;
  final bool confirmed;

  bool get isDailyBase {
    return role == FixedTravelPlaceRole.dailyBase;
  }

  bool get isValid {
    return id.trim().isNotEmpty &&
        !id.contains('/') &&
        name.trim().isNotEmpty &&
        location.isValid;
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id.trim(),
      'name': name.trim(),
      'role': role.name,
      'location': location.toJson(),
      'notes': notes,
      'confirmed': confirmed,
    };
  }

  FixedTravelPlace copyWith({
    String? id,
    String? name,
    FixedTravelPlaceRole? role,
    TravelLocation? location,
    Object? notes = _unset,
    bool? confirmed,
  }) {
    return FixedTravelPlace(
      id: id ?? this.id,
      name: name ?? this.name,
      role: role ?? this.role,
      location: location ?? this.location,
      notes: identical(notes, _unset) ? this.notes : notes as String?,
      confirmed: confirmed ?? this.confirmed,
    );
  }
}

class TravelContext {
  TravelContext({
    this.schemaVersion = 1,
    this.revision = 0,
    this.stage = TravelContextStage.collecting,
    this.startingLocation,
    this.tripStartDate,
    this.tripEndDate,
    this.dailyStartTime,
    this.dailyEndTime,
    this.availableTimeDescription,
    this.travelPartyDescription,
    this.travellerCount,
    this.travellerType,
    List<String> travelModes = const <String>[],
    List<TravelRequestGroup> requestGroups = const <TravelRequestGroup>[],
    List<String> preferences = const <String>[],
    List<String> accessibilityNeeds = const <String>[],
    List<String> avoidances = const <String>[],
    List<FixedTravelPlace> fixedPlaces = const <FixedTravelPlace>[],
    List<String> selectedPlaceIds = const <String>[],
    List<String> missingFields = const <String>[],
    List<String> uncertainties = const <String>[],
    this.confirmationSummary,
    this.isConfirmed = false,
    this.allowOverlongRoute = false,
  }) : travelModes = List<String>.unmodifiable(_normalizedStrings(travelModes)),
       requestGroups = List<TravelRequestGroup>.unmodifiable(
         _uniqueRequestGroups(requestGroups),
       ),
       preferences = List<String>.unmodifiable(_normalizedStrings(preferences)),
       accessibilityNeeds = List<String>.unmodifiable(
         _normalizedStrings(accessibilityNeeds),
       ),
       avoidances = List<String>.unmodifiable(_normalizedStrings(avoidances)),
       fixedPlaces = List<FixedTravelPlace>.unmodifiable(
         _uniqueFixedPlaces(fixedPlaces),
       ),
       selectedPlaceIds = List<String>.unmodifiable(
         _normalizedStrings(selectedPlaceIds),
       ),
       missingFields = List<String>.unmodifiable(
         _normalizedStrings(missingFields),
       ),
       uncertainties = List<String>.unmodifiable(
         _normalizedStrings(uncertainties),
       );

  static const Object _unset = Object();

  factory TravelContext.fromJson(Map<String, dynamic> json) {
    final rawStartingLocation = _mapValue(json['startingLocation']);

    final rawRequestGroups = json['requestGroups'];
    final requestGroups = <TravelRequestGroup>[];

    if (rawRequestGroups is List) {
      for (final rawGroup in rawRequestGroups) {
        final groupMap = _mapValue(rawGroup);

        if (groupMap == null) {
          continue;
        }

        final group = TravelRequestGroup.fromJson(groupMap);

        if (group.isValid) {
          requestGroups.add(group);
        }
      }
    }

    final rawFixedPlaces = json['fixedPlaces'];
    final fixedPlaces = <FixedTravelPlace>[];

    if (rawFixedPlaces is List) {
      for (final rawPlace in rawFixedPlaces) {
        final placeMap = _mapValue(rawPlace);

        if (placeMap == null) {
          continue;
        }

        final place = FixedTravelPlace.fromJson(placeMap);

        if (place.isValid) {
          fixedPlaces.add(place);
        }
      }
    }

    return TravelContext(
      schemaVersion: _integerValue(json['schemaVersion']) ?? 1,
      revision: _integerValue(json['revision']) ?? 0,
      stage:
          _enumByName(TravelContextStage.values, _stringValue(json['stage'])) ??
          TravelContextStage.collecting,
      startingLocation: rawStartingLocation == null
          ? null
          : TravelLocation.fromJson(rawStartingLocation),
      tripStartDate: _parseDate(json['tripStartDate']),
      tripEndDate: _parseDate(json['tripEndDate']),
      dailyStartTime: _normalizeTime(_stringValue(json['dailyStartTime'])),
      dailyEndTime: _normalizeTime(_stringValue(json['dailyEndTime'])),
      availableTimeDescription: _stringValue(json['availableTimeDescription']),
      travelPartyDescription: _stringValue(json['travelPartyDescription']),
      travellerCount: _integerValue(json['travellerCount']),
      travellerType:
          _enumByName(
            TravellerType.values,
            _stringValue(json['travellerType']),
          ) ??
          TravellerType.unknown,
      travelModes: _stringList(json['travelModes']),
      requestGroups: requestGroups,
      preferences: _stringList(json['preferences']),
      accessibilityNeeds: _stringList(json['accessibilityNeeds']),
      avoidances: _stringList(json['avoidances']),
      fixedPlaces: fixedPlaces,
      selectedPlaceIds: _stringList(json['selectedPlaceIds']),
      missingFields: _stringList(
        json['missingFields'],
      ).where((value) => value != 'roomCount').toList(),
      uncertainties: _stringList(json['uncertainties']),
      confirmationSummary: _stringValue(json['confirmationSummary']),
      isConfirmed: json['isConfirmed'] == true,
      allowOverlongRoute: json['allowOverlongRoute'] == true,
    );
  }

  final int schemaVersion;
  final int revision;
  final TravelContextStage stage;

  final TravelLocation? startingLocation;

  final DateTime? tripStartDate;
  final DateTime? tripEndDate;

  /// Stored as HH:mm:ss when available.
  final String? dailyStartTime;

  /// Stored as HH:mm:ss when available.
  final String? dailyEndTime;

  /// Preserves natural wording such as "two full days" or
  /// "until Sunday afternoon".
  final String? availableTimeDescription;

  final String? travelPartyDescription;
  final int? travellerCount;
  final TravellerType? travellerType;

  /// Natural transport descriptions are preserved so the backend can map
  /// them to supported route profiles for each segment.
  final List<String> travelModes;

  /// One group per requested result type or intent, such as temples
  /// and seafood restaurants.
  final List<TravelRequestGroup> requestGroups;

  final List<String> preferences;
  final List<String> accessibilityNeeds;
  final List<String> avoidances;

  /// Includes an already-booked hotel or any place the traveller requires.
  final List<FixedTravelPlace> fixedPlaces;

  /// Place identifiers selected through natural-language messages.
  final List<String> selectedPlaceIds;

  /// Backend-provided fields that still need to be collected.
  final List<String> missingFields;

  /// Backend-provided details that need clarification.
  final List<String> uncertainties;

  final String? confirmationSummary;
  final bool isConfirmed;

  /// True only after the traveller explicitly accepts an overlong route.
  final bool allowOverlongRoute;

  bool get hasRequestedPlaces {
    return requestGroups.isNotEmpty;
  }

  bool get hasMissingInformation {
    return missingFields.isNotEmpty;
  }

  bool get hasUncertainties {
    return uncertainties.isNotEmpty;
  }

  bool get needsClarification {
    return hasMissingInformation || hasUncertainties;
  }

  bool get hasBookedDailyBase {
    return fixedPlaces.any((place) => place.isDailyBase);
  }

  bool get hasRouteReadyDailyBase {
    return fixedPlaces.any(
      (place) =>
          place.isDailyBase && place.confirmed && place.location.isRouteReady,
    );
  }

  bool get hasTripPeriod {
    return tripDurationDays != null;
  }

  int? get tripDurationDays {
    final startDate = tripStartDate;
    final endDate = tripEndDate;

    if (startDate == null || endDate == null) {
      return null;
    }

    final normalizedStartDate = DateTime(
      startDate.year,
      startDate.month,
      startDate.day,
    );

    final normalizedEndDate = DateTime(
      endDate.year,
      endDate.month,
      endDate.day,
    );

    final difference = normalizedEndDate.difference(normalizedStartDate).inDays;

    if (difference < 0) {
      return null;
    }

    return difference + 1;
  }

  bool get isReadyForConfirmation {
    final hasRouteAnchor = startingLocation != null || hasBookedDailyBase;

    return hasRequestedPlaces &&
        hasRouteAnchor &&
        hasTripPeriod &&
        !needsClarification;
  }

  bool get canGenerateRecommendations {
    return isConfirmed &&
        isReadyForConfirmation &&
        stage != TravelContextStage.collecting;
  }

  Map<String, dynamic> toJson() {
    return {
      'schemaVersion': schemaVersion,
      'revision': revision,
      'stage': stage.name,
      'startingLocation': startingLocation?.toJson(),
      'tripStartDate': _formatDate(tripStartDate),
      'tripEndDate': _formatDate(tripEndDate),
      'dailyStartTime': dailyStartTime,
      'dailyEndTime': dailyEndTime,
      'availableTimeDescription': availableTimeDescription,
      'travelPartyDescription': travelPartyDescription,
      'travellerCount': travellerCount,
      'travellerType': travellerType?.name,
      'travelModes': travelModes,
      'requestGroups': requestGroups.map((group) => group.toJson()).toList(),
      'preferences': preferences,
      'accessibilityNeeds': accessibilityNeeds,
      'avoidances': avoidances,
      'fixedPlaces': fixedPlaces.map((place) => place.toJson()).toList(),
      'selectedPlaceIds': selectedPlaceIds,
      'missingFields': missingFields,
      'uncertainties': uncertainties,
      'confirmationSummary': confirmationSummary,
      'isConfirmed': isConfirmed,
      'allowOverlongRoute': allowOverlongRoute,
    };
  }

  TravelContext copyWith({
    int? schemaVersion,
    int? revision,
    TravelContextStage? stage,
    Object? startingLocation = _unset,
    Object? tripStartDate = _unset,
    Object? tripEndDate = _unset,
    Object? dailyStartTime = _unset,
    Object? dailyEndTime = _unset,
    Object? availableTimeDescription = _unset,
    Object? travelPartyDescription = _unset,
    Object? travellerCount = _unset,
    Object? travellerType = _unset,
    List<String>? travelModes,
    List<TravelRequestGroup>? requestGroups,
    List<String>? preferences,
    List<String>? accessibilityNeeds,
    List<String>? avoidances,
    List<FixedTravelPlace>? fixedPlaces,
    List<String>? selectedPlaceIds,
    List<String>? missingFields,
    List<String>? uncertainties,
    Object? confirmationSummary = _unset,
    bool? isConfirmed,
    bool? allowOverlongRoute,
  }) {
    return TravelContext(
      schemaVersion: schemaVersion ?? this.schemaVersion,
      revision: revision ?? this.revision,
      stage: stage ?? this.stage,
      startingLocation: identical(startingLocation, _unset)
          ? this.startingLocation
          : startingLocation as TravelLocation?,
      tripStartDate: identical(tripStartDate, _unset)
          ? this.tripStartDate
          : tripStartDate as DateTime?,
      tripEndDate: identical(tripEndDate, _unset)
          ? this.tripEndDate
          : tripEndDate as DateTime?,
      dailyStartTime: identical(dailyStartTime, _unset)
          ? this.dailyStartTime
          : dailyStartTime as String?,
      dailyEndTime: identical(dailyEndTime, _unset)
          ? this.dailyEndTime
          : dailyEndTime as String?,
      availableTimeDescription: identical(availableTimeDescription, _unset)
          ? this.availableTimeDescription
          : availableTimeDescription as String?,
      travelPartyDescription: identical(travelPartyDescription, _unset)
          ? this.travelPartyDescription
          : travelPartyDescription as String?,
      travellerCount: identical(travellerCount, _unset)
          ? this.travellerCount
          : travellerCount as int?,
      travellerType: identical(travellerType, _unset)
          ? this.travellerType
          : travellerType as TravellerType?,
      travelModes: travelModes ?? this.travelModes,
      requestGroups: requestGroups ?? this.requestGroups,
      preferences: preferences ?? this.preferences,
      accessibilityNeeds: accessibilityNeeds ?? this.accessibilityNeeds,
      avoidances: avoidances ?? this.avoidances,
      fixedPlaces: fixedPlaces ?? this.fixedPlaces,
      selectedPlaceIds: selectedPlaceIds ?? this.selectedPlaceIds,
      missingFields: missingFields ?? this.missingFields,
      uncertainties: uncertainties ?? this.uncertainties,
      confirmationSummary: identical(confirmationSummary, _unset)
          ? this.confirmationSummary
          : confirmationSummary as String?,
      isConfirmed: isConfirmed ?? this.isConfirmed,
      allowOverlongRoute: allowOverlongRoute ?? this.allowOverlongRoute,
    );
  }
}

List<TravelRequestGroup> _uniqueRequestGroups(List<TravelRequestGroup> groups) {
  final uniqueGroups = <String, TravelRequestGroup>{};

  for (final group in groups) {
    final id = group.id.trim();

    if (id.isEmpty) {
      continue;
    }

    uniqueGroups[id] = group;
  }

  return uniqueGroups.values.toList();
}

List<FixedTravelPlace> _uniqueFixedPlaces(List<FixedTravelPlace> places) {
  final uniquePlaces = <String, FixedTravelPlace>{};

  for (final place in places) {
    final id = place.id.trim();

    if (id.isEmpty) {
      continue;
    }

    uniquePlaces[id] = place;
  }

  return uniquePlaces.values.toList();
}

List<String> _normalizedStrings(Iterable<String> values) {
  final normalizedValues = <String>[];
  final seenValues = <String>{};

  for (final value in values) {
    final normalized = value.trim();

    if (normalized.isEmpty) {
      continue;
    }

    final comparisonValue = normalized.toLowerCase();

    if (seenValues.add(comparisonValue)) {
      normalizedValues.add(normalized);
    }
  }

  return normalizedValues;
}

List<String> _stringList(dynamic value) {
  if (value is String) {
    return _normalizedStrings([value]);
  }

  if (value is! Iterable) {
    return const <String>[];
  }

  return _normalizedStrings(value.whereType<String>());
}

Map<String, dynamic>? _mapValue(dynamic value) {
  if (value is Map<String, dynamic>) {
    return Map<String, dynamic>.from(value);
  }

  if (value is Map) {
    return value.map((key, item) => MapEntry(key.toString(), item));
  }

  return null;
}

String? _stringValue(dynamic value) {
  if (value is! String) {
    return null;
  }

  final normalized = value.trim();

  return normalized.isEmpty ? null : normalized;
}

double? _doubleValue(dynamic value) {
  if (value is num) {
    return value.toDouble();
  }

  return null;
}

int? _integerValue(dynamic value) {
  if (value is int) {
    return value;
  }

  if (value is num) {
    return value.toInt();
  }

  return null;
}

T? _enumByName<T extends Enum>(List<T> values, String? name) {
  if (name == null) {
    return null;
  }

  for (final value in values) {
    if (value.name == name) {
      return value;
    }
  }

  return null;
}

String? _formatDate(DateTime? date) {
  if (date == null) {
    return null;
  }

  final year = date.year.toString().padLeft(4, '0');
  final month = date.month.toString().padLeft(2, '0');
  final day = date.day.toString().padLeft(2, '0');

  return '$year-$month-$day';
}

DateTime? _parseDate(dynamic value) {
  if (value is DateTime) {
    return DateTime(value.year, value.month, value.day);
  }

  if (value is! String) {
    return null;
  }

  final parsed = DateTime.tryParse(value.trim());

  if (parsed == null) {
    return null;
  }

  return DateTime(parsed.year, parsed.month, parsed.day);
}

String? _normalizeTime(String? value) {
  if (value == null) {
    return null;
  }

  final match = RegExp(
    r'^([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$',
  ).firstMatch(value);

  if (match == null) {
    return null;
  }

  final hour = match.group(1);
  final minute = match.group(2);
  final second = match.group(3) ?? '00';

  return '$hour:$minute:$second';
}
