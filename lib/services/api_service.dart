import 'dart:async';
import 'dart:convert';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;
import 'package:trip_logic/models/conversation_turn_request.dart';
import 'package:trip_logic/models/conversation_turn_response.dart';

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() {
    if (statusCode == null) {
      return message;
    }

    return 'API error $statusCode: $message';
  }
}

class RouteLocationInput {
  const RouteLocationInput({required this.latitude, required this.longitude});

  final double latitude;
  final double longitude;

  Map<String, dynamic> toJson() {
    return {'latitude': latitude, 'longitude': longitude};
  }
}

class RecommendationLocationInput {
  const RecommendationLocationInput({
    required this.displayName,
    required this.latitude,
    required this.longitude,
    required this.source,
  });

  final String displayName;
  final double latitude;
  final double longitude;
  final String source;

  Map<String, dynamic> toJson() {
    return {
      'displayName': displayName,
      'latitude': latitude,
      'longitude': longitude,
      'source': source,
    };
  }
}

class RecommendationCategoryInput {
  const RecommendationCategoryInput({required this.id, required this.name});

  final String id;
  final String name;

  Map<String, dynamic> toJson() {
    return {'id': id, 'name': name};
  }
}

class ApiService {
  ApiService({FirebaseAuth? firebaseAuth, http.Client? client, String? baseUrl})
    : _firebaseAuth = firebaseAuth ?? FirebaseAuth.instance,
      _client = client ?? http.Client(),
      _ownsClient = client == null,
      _baseUrl = _normalizeBaseUrl(baseUrl ?? _configuredBaseUrl);

  static const String _configuredBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static const Duration _requestTimeout = Duration(seconds: 45);

  static const int _maximumPlaceRadiusMeters = 100000;
  static const int _maximumPlaceResults = 50;
  static const int _maximumPlaceCategories = 3;

  static const Set<String> _supportedPlaceSortOptions = {
    'RELEVANCE',
    'RATING',
    'DISTANCE',
    'POPULARITY',
  };

  static const int _maximumRouteLocations = 20;

  static const Set<String> _supportedTravelModes = {
    'driving',
    'walking',
    'cycling',
  };

  static const Set<String> _supportedRecommendationTypes = {
    'attraction',
    'hotel',
    'restaurant',
  };

  static const Set<String> _supportedRecommendationTravelModes = {
    'driving',
    'walking',
    'cycling',
  };

  static const Set<String> _supportedTravelPartners = {
    'soloTraveller',
    'couple',
    'family',
    'friendsGroup',
    'seniorTravellers',
  };

  static const Set<String> _supportedLocationSources = {'current', 'selected'};

  final FirebaseAuth _firebaseAuth;
  final http.Client _client;
  final bool _ownsClient;
  final String _baseUrl;

  static String _normalizeBaseUrl(String value) {
    var normalizedValue = value.trim();

    while (normalizedValue.endsWith('/')) {
      normalizedValue = normalizedValue.substring(
        0,
        normalizedValue.length - 1,
      );
    }

    final uri = Uri.tryParse(normalizedValue);

    if (uri == null ||
        !uri.hasScheme ||
        uri.host.isEmpty ||
        (uri.scheme != 'http' && uri.scheme != 'https')) {
      throw ArgumentError.value(
        value,
        'baseUrl',
        'Enter a valid HTTP or HTTPS backend URL.',
      );
    }

    return normalizedValue;
  }

  static String _formatIsoDate(DateTime date) {
    final year = date.year.toString().padLeft(4, '0');
    final month = date.month.toString().padLeft(2, '0');
    final day = date.day.toString().padLeft(2, '0');

    return '$year-$month-$day';
  }

  static bool _isValidLocalTime(String value) {
    final match = RegExp(
      r'^([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$',
    ).firstMatch(value.trim());

    return match != null;
  }

  Future<Map<String, dynamic>> getAuthenticatedUser() {
    return _getJson('/auth/me');
  }

  Future<ConversationTurnResponse> processConversationTurn(
    ConversationTurnRequest request,
  ) async {
    if (!request.isValid) {
      throw const ApiException('The conversation request is invalid.');
    }

    final responseData = await _postJson(
      '/conversation/turn',
      body: request.toJson(),
    );

    late final ConversationTurnResponse response;

    try {
      response = ConversationTurnResponse.fromJson(responseData);
    } on FormatException catch (error) {
      throw ApiException(
        'The server returned an invalid conversation response: '
        '${error.message}',
      );
    }

    if (response.chatId != request.chatId) {
      throw const ApiException(
        'The conversation response used an unexpected chat ID.',
      );
    }

    if (response.turnId != request.turnId) {
      throw const ApiException(
        'The conversation response used an unexpected turn ID.',
      );
    }

    if (response.acceptedTravellerMessageId != request.travellerMessageId) {
      throw const ApiException(
        'The server accepted an unexpected traveller message.',
      );
    }

    if (response.contextRevision < request.expectedContextRevision) {
      throw const ApiException(
        'The server returned an outdated travel context.',
      );
    }

    return response;
  }

  Future<Map<String, dynamic>> searchLocations(String query) {
    final normalizedQuery = query.trim();

    if (normalizedQuery.length < 2) {
      throw const ApiException('Enter at least two characters to search.');
    }

    return _getJson(
      '/locations/search',
      queryParameters: {'query': normalizedQuery},
    );
  }

  Future<Map<String, dynamic>> getWeatherForecast({
    required double latitude,
    required double longitude,
    required DateTime visitDate,
  }) {
    if (!latitude.isFinite || latitude < -90 || latitude > 90) {
      throw const ApiException('Latitude must be between -90 and 90.');
    }

    if (!longitude.isFinite || longitude < -180 || longitude > 180) {
      throw const ApiException('Longitude must be between -180 and 180.');
    }

    return _getJson(
      '/weather/forecast',
      queryParameters: {
        'latitude': latitude.toString(),
        'longitude': longitude.toString(),
        'visit_date': _formatIsoDate(visitDate),
      },
    );
  }

  Future<Map<String, dynamic>> searchPlaces({
    required String query,
    required double latitude,
    required double longitude,
    List<String> categoryIds = const [],
    int radius = 15000,
    int limit = 6,
    String sort = 'RELEVANCE',
  }) {
    final normalizedQuery = query.trim();

    if (normalizedQuery.length < 2) {
      throw const ApiException(
        'Enter at least two characters to search for places.',
      );
    }

    if (normalizedQuery.length > 80) {
      throw const ApiException('The place search cannot exceed 80 characters.');
    }

    if (!latitude.isFinite || latitude < -90 || latitude > 90) {
      throw const ApiException('Latitude must be between -90 and 90.');
    }

    if (!longitude.isFinite || longitude < -180 || longitude > 180) {
      throw const ApiException('Longitude must be between -180 and 180.');
    }

    if (radius < 1 || radius > _maximumPlaceRadiusMeters) {
      throw const ApiException(
        'The search radius must be between 1 and 100000 metres.',
      );
    }

    if (limit < 1 || limit > _maximumPlaceResults) {
      throw const ApiException(
        'The place result limit must be between 1 and 50.',
      );
    }

    final normalizedSort = sort.trim().toUpperCase();

    if (!_supportedPlaceSortOptions.contains(normalizedSort)) {
      throw const ApiException('The place sort option is invalid.');
    }

    final normalizedCategoryIds = categoryIds
        .map((categoryId) => categoryId.trim())
        .where((categoryId) => categoryId.isNotEmpty)
        .toSet()
        .toList();

    if (normalizedCategoryIds.length > _maximumPlaceCategories) {
      throw const ApiException(
        'A maximum of three place categories can be selected.',
      );
    }

    final validCategoryIdPattern = RegExp(r'^[A-Za-z0-9]+$');

    for (final categoryId in normalizedCategoryIds) {
      if (categoryId.length > 64 ||
          !validCategoryIdPattern.hasMatch(categoryId)) {
        throw const ApiException(
          'Every place category ID must contain letters or numbers only.',
        );
      }
    }

    final queryParameters = <String, dynamic>{
      'query': normalizedQuery,
      'latitude': latitude.toString(),
      'longitude': longitude.toString(),
      'radius': radius.toString(),
      'limit': limit.toString(),
      'sort': normalizedSort,
    };

    if (normalizedCategoryIds.isNotEmpty) {
      queryParameters['category_ids'] = normalizedCategoryIds;
    }

    return _getJson('/places/search', queryParameters: queryParameters);
  }

  Future<Map<String, dynamic>> getRouteMatrix({
    required List<RouteLocationInput> locations,
    required String travelMode,
  }) {
    if (locations.length < 2) {
      throw const ApiException('At least two route locations are required.');
    }

    if (locations.length > _maximumRouteLocations) {
      throw const ApiException(
        'A maximum of twenty route locations can be processed.',
      );
    }

    final normalizedTravelMode = travelMode.trim().toLowerCase();

    if (!_supportedTravelModes.contains(normalizedTravelMode)) {
      throw const ApiException(
        'Travel mode must be car, walking, cycling, or wheelchair.',
      );
    }

    for (final location in locations) {
      if (!location.latitude.isFinite ||
          location.latitude < -90 ||
          location.latitude > 90) {
        throw const ApiException(
          'Every route latitude must be between -90 and 90.',
        );
      }

      if (!location.longitude.isFinite ||
          location.longitude < -180 ||
          location.longitude > 180) {
        throw const ApiException(
          'Every route longitude must be between -180 and 180.',
        );
      }
    }

    return _postJson(
      '/routes/matrix',
      body: {
        'travelMode': normalizedTravelMode,
        'locations': locations.map((location) => location.toJson()).toList(),
      },
    );
  }

  Future<Map<String, dynamic>> generateRecommendations({
    required String recommendationType,
    required RecommendationLocationInput location,
    required String travelMode,
    required String travelPartner,
    required List<RecommendationCategoryInput> categories,
    DateTime? visitDate,
    String? startTime,
    int? visitDurationMinutes,
    DateTime? checkInDate,
    DateTime? checkOutDate,
    int? travellers,
  }) {
    final normalizedType = recommendationType.trim().toLowerCase();

    final normalizedTravelMode = travelMode.trim().toLowerCase();

    final normalizedTravelPartner = travelPartner.trim().toLowerCase();

    final normalizedLocationSource = location.source.trim().toLowerCase();

    final normalizedDisplayName = location.displayName.trim();

    if (!_supportedRecommendationTypes.contains(normalizedType)) {
      throw const ApiException(
        'Recommendation type must be attraction, hotel, or restaurant.',
      );
    }

    if (!_supportedRecommendationTravelModes.contains(normalizedTravelMode)) {
      throw const ApiException(
        'Travel mode must be car, walking, cycling, or wheelchair.',
      );
    }

    if (!_supportedTravelPartners.contains(normalizedTravelPartner)) {
      throw const ApiException('The selected travel partner type is invalid.');
    }

    if (!_supportedLocationSources.contains(normalizedLocationSource)) {
      throw const ApiException('The selected location source is invalid.');
    }

    if (normalizedDisplayName.length < 2 ||
        normalizedDisplayName.length > 150) {
      throw const ApiException(
        'The location name must contain between 2 and 150 characters.',
      );
    }

    if (!location.latitude.isFinite ||
        location.latitude < -90 ||
        location.latitude > 90) {
      throw const ApiException(
        'The location latitude must be between -90 and 90.',
      );
    }

    if (!location.longitude.isFinite ||
        location.longitude < -180 ||
        location.longitude > 180) {
      throw const ApiException(
        'The location longitude must be between -180 and 180.',
      );
    }

    final uniqueCategories = <String, RecommendationCategoryInput>{};

    final validCategoryIdPattern = RegExp(r'^[A-Za-z0-9]+$');

    for (final category in categories) {
      final categoryId = category.id.trim();
      final categoryName = category.name.trim();

      if (categoryId.isEmpty ||
          categoryId.length > 64 ||
          !validCategoryIdPattern.hasMatch(categoryId)) {
        throw const ApiException(
          'Every category ID must contain letters or numbers only.',
        );
      }

      if (categoryName.length < 2 || categoryName.length > 100) {
        throw const ApiException(
          'Every category name must contain between 2 and 100 characters.',
        );
      }

      uniqueCategories[categoryId] = RecommendationCategoryInput(
        id: categoryId,
        name: categoryName,
      );
    }

    if (uniqueCategories.isEmpty) {
      throw const ApiException('Select at least one category.');
    }

    if (uniqueCategories.length > _maximumPlaceCategories) {
      throw const ApiException(
        'A maximum of three categories can be selected.',
      );
    }

    final body = <String, dynamic>{
      'recommendationType': normalizedType,
      'location': RecommendationLocationInput(
        displayName: normalizedDisplayName,
        latitude: location.latitude,
        longitude: location.longitude,
        source: normalizedLocationSource,
      ).toJson(),
      'travelMode': normalizedTravelMode,
      'travelPartner': normalizedTravelPartner,
      'categories': uniqueCategories.values
          .map((category) => category.toJson())
          .toList(),
    };

    if (normalizedType == 'attraction' || normalizedType == 'restaurant') {
      if (visitDate == null) {
        throw const ApiException('A visit date is required.');
      }

      final normalizedStartTime = startTime?.trim() ?? '';

      if (!_isValidLocalTime(normalizedStartTime)) {
        throw const ApiException(
          'Enter the start time using HH:mm or HH:mm:ss.',
        );
      }

      if (visitDurationMinutes == null ||
          visitDurationMinutes < 30 ||
          visitDurationMinutes > 720) {
        throw const ApiException(
          'Visit duration must be between 30 and 720 minutes.',
        );
      }

      if (checkInDate != null || checkOutDate != null || travellers != null) {
        throw const ApiException(
          'Hotel fields cannot be used for attraction or restaurant requests.',
        );
      }

      body.addAll({
        'visitDate': _formatIsoDate(visitDate),
        'startTime': normalizedStartTime,
        'visitDurationMinutes': visitDurationMinutes,
      });
    } else {
      if (checkInDate == null || checkOutDate == null) {
        throw const ApiException('Check-in and check-out dates are required.');
      }

      final normalizedCheckInDate = DateTime(
        checkInDate.year,
        checkInDate.month,
        checkInDate.day,
      );

      final normalizedCheckOutDate = DateTime(
        checkOutDate.year,
        checkOutDate.month,
        checkOutDate.day,
      );

      if (!normalizedCheckOutDate.isAfter(normalizedCheckInDate)) {
        throw const ApiException('Check-out date must be after check-in date.');
      }

      if (travellers == null || travellers < 1 || travellers > 20) {
        throw const ApiException('Travellers must be between 1 and 20.');
      }

      if (visitDate != null ||
          startTime != null ||
          visitDurationMinutes != null) {
        throw const ApiException(
          'Visit-time fields cannot be used for hotel requests.',
        );
      }

      body.addAll({
        'checkInDate': _formatIsoDate(normalizedCheckInDate),
        'checkOutDate': _formatIsoDate(normalizedCheckOutDate),
        'travellers': travellers,
      });
    }

    return _postJson('/recommendations/generate', body: body);
  }

  Future<Map<String, dynamic>> _getJson(
    String path, {
    Map<String, dynamic>? queryParameters,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);

    var idToken = await _getFirebaseIdToken();
    var response = await _sendGet(uri: uri, idToken: idToken);

    // Retry once with a newly refreshed Firebase token.
    if (response.statusCode == 401) {
      idToken = await _getFirebaseIdToken(forceRefresh: true);

      response = await _sendGet(uri: uri, idToken: idToken);
    }

    final responseData = _decodeResponse(response);

    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = responseData['detail'];

      throw ApiException(
        detail is String && detail.trim().isNotEmpty
            ? detail.trim()
            : 'The server returned an error.',
        statusCode: response.statusCode,
      );
    }

    return responseData;
  }

  Future<Map<String, dynamic>> _postJson(
    String path, {
    required Map<String, dynamic> body,
  }) async {
    final uri = Uri.parse('$_baseUrl$path');

    var idToken = await _getFirebaseIdToken();

    var response = await _sendPost(uri: uri, idToken: idToken, body: body);

    if (response.statusCode == 401) {
      idToken = await _getFirebaseIdToken(forceRefresh: true);

      response = await _sendPost(uri: uri, idToken: idToken, body: body);
    }

    final responseData = _decodeResponse(response);

    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = responseData['detail'];

      throw ApiException(
        detail is String && detail.trim().isNotEmpty
            ? detail.trim()
            : 'The server returned an error.',
        statusCode: response.statusCode,
      );
    }

    return responseData;
  }

  Future<http.Response> _sendGet({
    required Uri uri,
    required String idToken,
  }) async {
    try {
      return await _client
          .get(
            uri,
            headers: {
              'Accept': 'application/json',
              'Authorization': 'Bearer $idToken',
            },
          )
          .timeout(_requestTimeout);
    } on TimeoutException {
      throw const ApiException('The server took too long to respond.');
    } on http.ClientException catch (error) {
      throw ApiException(
        'Unable to connect to the server: '
        '${error.message}',
      );
    }
  }

  Future<http.Response> _sendPost({
    required Uri uri,
    required String idToken,
    required Map<String, dynamic> body,
  }) async {
    try {
      return await _client
          .post(
            uri,
            headers: {
              'Accept': 'application/json',
              'Authorization': 'Bearer $idToken',
              'Content-Type': 'application/json',
            },
            body: jsonEncode(body),
          )
          .timeout(_requestTimeout);
    } on TimeoutException {
      throw const ApiException('The server took too long to respond.');
    } on http.ClientException catch (error) {
      throw ApiException(
        'Unable to connect to the server: '
        '${error.message}',
      );
    }
  }

  Future<String> _getFirebaseIdToken({bool forceRefresh = false}) async {
    final user = _firebaseAuth.currentUser;

    if (user == null) {
      throw const ApiException(
        'You must be signed in to use this feature.',
        statusCode: 401,
      );
    }

    try {
      final idToken = await user.getIdToken(forceRefresh);

      if (idToken == null || idToken.trim().isEmpty) {
        throw const ApiException(
          'Unable to create an authentication token.',
          statusCode: 401,
        );
      }

      return idToken.trim();
    } on FirebaseAuthException catch (error) {
      throw ApiException(
        error.message ?? 'Unable to authenticate your account.',
        statusCode: 401,
      );
    }
  }

  Map<String, dynamic> _decodeResponse(http.Response response) {
    if (response.bodyBytes.isEmpty) {
      return <String, dynamic>{};
    }

    try {
      final decodedData = jsonDecode(utf8.decode(response.bodyBytes));

      if (decodedData is Map<String, dynamic>) {
        return decodedData;
      }

      if (decodedData is Map) {
        return Map<String, dynamic>.from(decodedData);
      }

      throw const ApiException('The server returned an unexpected response.');
    } on FormatException {
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return {'detail': 'The server returned an invalid response.'};
      }

      throw const ApiException('The server returned invalid JSON.');
    }
  }

  void close() {
    if (_ownsClient) {
      _client.close();
    }
  }
}
