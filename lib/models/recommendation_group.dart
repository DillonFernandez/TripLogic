import 'package:trip_logic/models/travel_context.dart';

class RecommendationGroup {
  const RecommendationGroup({
    required this.requestGroupId,
    required this.recommendationType,
    required this.result,
    required this.required,
    this.travellerQuery,
    this.requestedCount,
  });

  factory RecommendationGroup.fromJson(Map<String, dynamic> json) {
    final resultMap = _mapValue(json['result']);

    if (resultMap == null) {
      throw const FormatException(
        'Recommendation group result must be a JSON object.',
      );
    }

    return RecommendationGroup(
      requestGroupId: _requiredString(json, 'requestGroupId'),
      recommendationType:
          _enumByName(
            TravelRequestKind.values,
            _stringValue(json['recommendationType']),
          ) ??
          TravelRequestKind.unknown,
      travellerQuery: _stringValue(json['travellerQuery']),
      requestedCount: _integerValue(json['requestedCount']),
      required: json['required'] != false,
      result: RecommendationResult.fromJson(resultMap),
    );
  }

  final String requestGroupId;
  final TravelRequestKind recommendationType;
  final String? travellerQuery;
  final int? requestedCount;
  final bool required;
  final RecommendationResult result;

  bool get isValid {
    return requestGroupId.trim().isNotEmpty &&
        !requestGroupId.contains('/') &&
        recommendationType != TravelRequestKind.unknown &&
        (requestedCount == null || requestedCount! > 0);
  }
}

class RecommendationResult {
  RecommendationResult({
    required this.recommendationType,
    required this.count,
    required List<PlaceRecommendation> topRecommendations,
    required List<PlaceRecommendation> moreRecommendations,
    this.message,
  }) : topRecommendations = List<PlaceRecommendation>.unmodifiable(
         topRecommendations,
       ),
       moreRecommendations = List<PlaceRecommendation>.unmodifiable(
         moreRecommendations,
       );

  factory RecommendationResult.fromJson(Map<String, dynamic> json) {
    final topRecommendations = _placeRecommendationList(
      json['topRecommendations'],
    );

    final moreRecommendations = _placeRecommendationList(
      json['moreRecommendations'],
    );

    return RecommendationResult(
      recommendationType:
          _enumByName(
            TravelRequestKind.values,
            _stringValue(json['recommendationType']),
          ) ??
          TravelRequestKind.unknown,
      count:
          _integerValue(json['count']) ??
          topRecommendations.length + moreRecommendations.length,
      topRecommendations: topRecommendations,
      moreRecommendations: moreRecommendations,
      message: _stringValue(json['message']),
    );
  }

  final TravelRequestKind recommendationType;
  final int count;
  final List<PlaceRecommendation> topRecommendations;
  final List<PlaceRecommendation> moreRecommendations;
  final String? message;

  List<PlaceRecommendation> get allRecommendations {
    return List<PlaceRecommendation>.unmodifiable([
      ...topRecommendations,
      ...moreRecommendations,
    ]);
  }

  bool get isEmpty {
    return allRecommendations.isEmpty;
  }
}

class PlaceRecommendation {
  PlaceRecommendation({
    required this.id,
    required this.name,
    List<RecommendationPlaceCategory> categories =
        const <RecommendationPlaceCategory>[],
    this.location,
    this.latitude,
    this.longitude,
    this.distanceMeters,
    this.rating,
    this.hours,
    this.telephone,
    this.website,
    this.route,
    this.weatherSuitability,
    this.score,
    this.scoreBreakdown,
    this.explanation,
    this.rank,
  }) : categories = List<RecommendationPlaceCategory>.unmodifiable(categories);

  factory PlaceRecommendation.fromJson(Map<String, dynamic> json) {
    final rawCategories = json['categories'];

    final categories = <RecommendationPlaceCategory>[];

    if (rawCategories is List) {
      for (final rawCategory in rawCategories) {
        final categoryMap = _mapValue(rawCategory);

        if (categoryMap == null) {
          continue;
        }

        final category = RecommendationPlaceCategory.fromJson(categoryMap);

        if (category.isValid) {
          categories.add(category);
        }
      }
    }

    final locationMap = _mapValue(json['location']);

    final routeMap = _mapValue(json['route']);

    final weatherSuitabilityMap = _mapValue(json['weatherSuitability']);

    final scoreBreakdownMap = _mapValue(json['scoreBreakdown']);

    final hoursMap = _mapValue(json['hours']);
    final parsedHours = hoursMap == null
        ? null
        : RecommendationOpeningHours.fromJson(hoursMap);

    return PlaceRecommendation(
      id: _stringValue(json['id']) ?? '',
      name: _stringValue(json['name']) ?? '',
      categories: categories,
      location: locationMap == null
          ? null
          : RecommendationPlaceLocation.fromJson(locationMap),
      latitude: _doubleValue(json['latitude']),
      longitude: _doubleValue(json['longitude']),
      distanceMeters: _integerValue(json['distanceMeters']),
      rating: _ratingValue(json['rating']),
      hours: parsedHours?.hasVerifiedData == true ? parsedHours : null,
      telephone: _stringValue(json['telephone']),
      website: _stringValue(json['website']),
      route: routeMap == null ? null : RecommendationRoute.fromJson(routeMap),
      weatherSuitability: weatherSuitabilityMap == null
          ? null
          : RecommendationWeatherSuitability.fromJson(weatherSuitabilityMap),
      score: _doubleValue(json['score']),
      scoreBreakdown: scoreBreakdownMap == null
          ? null
          : RecommendationScoreBreakdown.fromJson(scoreBreakdownMap),
      explanation: _stringValue(json['explanation']),
      rank: _integerValue(json['rank']),
    );
  }

  final String id;
  final String name;
  final List<RecommendationPlaceCategory> categories;
  final RecommendationPlaceLocation? location;

  final double? latitude;
  final double? longitude;
  final int? distanceMeters;
  final double? rating;
  final RecommendationOpeningHours? hours;

  final String? telephone;
  final String? website;

  final RecommendationRoute? route;

  final RecommendationWeatherSuitability? weatherSuitability;

  final double? score;
  final RecommendationScoreBreakdown? scoreBreakdown;

  final String? explanation;
  final int? rank;

  bool get isValid {
    return id.trim().isNotEmpty && name.trim().isNotEmpty;
  }

  bool get hasCoordinates {
    return latitude != null && longitude != null;
  }
}

class RecommendationOpeningHours {
  RecommendationOpeningHours({
    required List<RecommendationOpeningInterval> regular,
    this.openNow,
    this.isLocalHoliday,
    this.display,
  }) : regular = List<RecommendationOpeningInterval>.unmodifiable(regular);

  factory RecommendationOpeningHours.fromJson(Map<String, dynamic> json) {
    final regular = <RecommendationOpeningInterval>[];
    final rawRegular = json['regular'];

    if (rawRegular is List) {
      for (final rawInterval in rawRegular) {
        final intervalMap = _mapValue(rawInterval);

        if (intervalMap == null) {
          continue;
        }

        final interval = RecommendationOpeningInterval.fromJson(intervalMap);

        if (interval != null) {
          regular.add(interval);
        }
      }
    }

    return RecommendationOpeningHours(
      regular: regular,
      openNow: json['openNow'] is bool ? json['openNow'] as bool : null,
      isLocalHoliday: json['isLocalHoliday'] is bool
          ? json['isLocalHoliday'] as bool
          : null,
      display: _stringValue(json['display']),
    );
  }

  final List<RecommendationOpeningInterval> regular;
  final bool? openNow;
  final bool? isLocalHoliday;
  final String? display;

  bool get hasVerifiedData {
    return regular.isNotEmpty ||
        openNow != null ||
        isLocalHoliday != null ||
        display != null;
  }
}

class RecommendationOpeningInterval {
  const RecommendationOpeningInterval({
    required this.day,
    required this.openingTime,
    required this.closingTime,
    this.overnight,
    this.allDay,
  });

  static RecommendationOpeningInterval? fromJson(Map<String, dynamic> json) {
    final day = _integerValue(json['day']);
    final openingTime = _stringValue(json['openingTime']);
    final closingTime = _stringValue(json['closingTime']);

    if (day == null ||
        day < 1 ||
        day > 7 ||
        openingTime == null ||
        !_isHoursTime(openingTime, allow24: false) ||
        closingTime == null ||
        !_isHoursTime(closingTime, allow24: true)) {
      return null;
    }

    return RecommendationOpeningInterval(
      day: day,
      openingTime: openingTime,
      closingTime: closingTime,
      overnight: json['overnight'] is bool ? json['overnight'] as bool : null,
      allDay: json['allDay'] is bool ? json['allDay'] as bool : null,
    );
  }

  final int day;
  final String openingTime;
  final String closingTime;
  final bool? overnight;
  final bool? allDay;
}

class RecommendationPlaceCategory {
  const RecommendationPlaceCategory({required this.name, this.id});

  factory RecommendationPlaceCategory.fromJson(Map<String, dynamic> json) {
    return RecommendationPlaceCategory(
      id: _stringValue(json['id']),
      name: _stringValue(json['name']) ?? '',
    );
  }

  final String? id;
  final String name;

  bool get isValid {
    return name.trim().isNotEmpty;
  }
}

class RecommendationPlaceLocation {
  const RecommendationPlaceLocation({
    this.address,
    this.locality,
    this.region,
    this.country,
    this.displayAddress,
  });

  factory RecommendationPlaceLocation.fromJson(Map<String, dynamic> json) {
    return RecommendationPlaceLocation(
      address: _stringValue(json['address']),
      locality: _stringValue(json['locality']),
      region: _stringValue(json['region']),
      country: _stringValue(json['country']),
      displayAddress: _stringValue(json['displayAddress']),
    );
  }

  final String? address;
  final String? locality;
  final String? region;
  final String? country;
  final String? displayAddress;
}

class RecommendationRoute {
  const RecommendationRoute({
    required this.available,
    this.travelMode,
    this.durationMinutes,
    this.distanceKilometres,
    this.availableTimeMinutes,
    this.remainingVisitMinutes,
    this.timeFeasible,
    this.outboundDurationSeconds,
    this.returnDurationSeconds,
  });

  factory RecommendationRoute.fromJson(Map<String, dynamic> json) {
    return RecommendationRoute(
      available: json['available'] == true,
      travelMode: _stringValue(json['travelMode']),
      durationMinutes: _doubleValue(json['durationMinutes']),
      distanceKilometres: _doubleValue(json['distanceKilometres']),
      availableTimeMinutes: _doubleValue(json['availableTimeMinutes']),
      remainingVisitMinutes: _doubleValue(json['remainingVisitMinutes']),
      timeFeasible: json['timeFeasible'] is bool
          ? json['timeFeasible'] as bool
          : null,
      outboundDurationSeconds: _doubleValue(json['outboundDurationSeconds']),
      returnDurationSeconds: _doubleValue(json['returnDurationSeconds']),
    );
  }

  final bool available;
  final String? travelMode;

  final double? durationMinutes;
  final double? distanceKilometres;

  final double? availableTimeMinutes;
  final double? remainingVisitMinutes;
  final bool? timeFeasible;

  final double? outboundDurationSeconds;
  final double? returnDurationSeconds;
}

class RecommendationWeatherSuitability {
  const RecommendationWeatherSuitability({
    this.status,
    this.environment,
    this.riskLevel,
    this.score,
    this.message,
  });

  factory RecommendationWeatherSuitability.fromJson(Map<String, dynamic> json) {
    return RecommendationWeatherSuitability(
      status: _stringValue(json['status']),
      environment: _stringValue(json['environment']),
      riskLevel: _stringValue(json['riskLevel']),
      score: _doubleValue(json['score']),
      message: _stringValue(json['message']),
    );
  }

  final String? status;
  final String? environment;
  final String? riskLevel;
  final double? score;
  final String? message;
}

class RecommendationScoreBreakdown {
  const RecommendationScoreBreakdown({
    this.category,
    this.route,
    this.weather,
    this.travelPartner,
    this.searchRelevance,
  });

  factory RecommendationScoreBreakdown.fromJson(Map<String, dynamic> json) {
    return RecommendationScoreBreakdown(
      category: _doubleValue(json['category']),
      route: _doubleValue(json['route']),
      weather: _doubleValue(json['weather']),
      travelPartner: _doubleValue(json['travelPartner']),
      searchRelevance: _doubleValue(json['searchRelevance']),
    );
  }

  final double? category;
  final double? route;
  final double? weather;
  final double? travelPartner;
  final double? searchRelevance;
}

List<PlaceRecommendation> _placeRecommendationList(dynamic value) {
  if (value is! List) {
    return const <PlaceRecommendation>[];
  }

  final recommendations = <PlaceRecommendation>[];

  for (final rawRecommendation in value) {
    final recommendationMap = _mapValue(rawRecommendation);

    if (recommendationMap == null) {
      continue;
    }

    final recommendation = PlaceRecommendation.fromJson(recommendationMap);

    if (recommendation.isValid) {
      recommendations.add(recommendation);
    }
  }

  return recommendations;
}

String _requiredString(Map<String, dynamic> json, String fieldName) {
  final value = _stringValue(json[fieldName]);

  if (value == null) {
    throw FormatException('$fieldName must be a non-empty string.');
  }

  return value;
}

String? _stringValue(dynamic value) {
  if (value is! String) {
    return null;
  }

  final normalized = value.trim();

  return normalized.isEmpty ? null : normalized;
}

int? _integerValue(dynamic value) {
  if (value is int) {
    return value;
  }

  if (value is num && value.isFinite) {
    final integerValue = value.toInt();

    if (value == integerValue) {
      return integerValue;
    }
  }

  return null;
}

double? _doubleValue(dynamic value) {
  if (value is num && value.isFinite) {
    return value.toDouble();
  }

  return null;
}

double? _ratingValue(dynamic value) {
  final rating = _doubleValue(value);

  if (rating == null || rating < 0 || rating > 10) {
    return null;
  }

  return rating;
}

bool _isHoursTime(String value, {required bool allow24}) {
  if (allow24 && value == '24:00') {
    return true;
  }

  return RegExp(r'^(?:[01]\d|2[0-3]):[0-5]\d$').hasMatch(value);
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
