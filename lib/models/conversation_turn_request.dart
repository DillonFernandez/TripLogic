enum ConversationTurnOperation { sendMessage, editMessage }

class ConversationDeviceLocation {
  const ConversationDeviceLocation({
    required this.latitude,
    required this.longitude,
    required this.capturedAt,
    this.accuracyMetres,
  });

  factory ConversationDeviceLocation.fromJson(Map<String, dynamic> json) {
    final latitude = _doubleValue(json['latitude']);
    final longitude = _doubleValue(json['longitude']);
    final capturedAt = _dateTimeValue(json['capturedAt']);
    final accuracyMetres = _doubleValue(json['accuracyMetres']);

    if (latitude == null || longitude == null || capturedAt == null) {
      throw const FormatException(
        'Device location requires latitude, longitude, and capturedAt.',
      );
    }

    return ConversationDeviceLocation(
      latitude: latitude,
      longitude: longitude,
      capturedAt: capturedAt,
      accuracyMetres: accuracyMetres,
    );
  }

  final double latitude;
  final double longitude;
  final double? accuracyMetres;
  final DateTime capturedAt;

  bool get isValid {
    return latitude.isFinite &&
        latitude >= -90 &&
        latitude <= 90 &&
        longitude.isFinite &&
        longitude >= -180 &&
        longitude <= 180 &&
        (accuracyMetres == null ||
            (accuracyMetres!.isFinite && accuracyMetres! >= 0));
  }

  Map<String, dynamic> toJson() {
    return {
      'latitude': latitude,
      'longitude': longitude,
      'accuracyMetres': accuracyMetres,
      'capturedAt': capturedAt.toUtc().toIso8601String(),
    };
  }
}

class ConversationTurnRequest {
  ConversationTurnRequest({
    required this.requestId,
    required this.operation,
    required this.travellerMessageId,
    required this.turnId,
    required this.travellerMessageSequence,
    required this.text,
    required this.clientCreatedAt,
    required this.expectedContextRevision,
    required this.chatId,
    this.deviceLocation,
  }) {
    _validate();
  }

  factory ConversationTurnRequest.newMessage({
    required String requestId,
    required String travellerMessageId,
    required String turnId,
    required int travellerMessageSequence,
    required String text,
    required int expectedContextRevision,
    required String chatId,
    ConversationDeviceLocation? deviceLocation,
    DateTime? clientCreatedAt,
  }) {
    return ConversationTurnRequest(
      requestId: requestId,
      operation: ConversationTurnOperation.sendMessage,
      chatId: chatId,
      travellerMessageId: travellerMessageId,
      turnId: turnId,
      travellerMessageSequence: travellerMessageSequence,
      text: text,
      clientCreatedAt: clientCreatedAt ?? DateTime.now(),
      expectedContextRevision: expectedContextRevision,
      deviceLocation: deviceLocation,
    );
  }

  factory ConversationTurnRequest.editMessage({
    required String requestId,
    required String chatId,
    required String travellerMessageId,
    required String turnId,
    required int travellerMessageSequence,
    required String replacementText,
    required int expectedContextRevision,
    ConversationDeviceLocation? deviceLocation,
    DateTime? clientCreatedAt,
  }) {
    return ConversationTurnRequest(
      requestId: requestId,
      operation: ConversationTurnOperation.editMessage,
      chatId: chatId,
      travellerMessageId: travellerMessageId,
      turnId: turnId,
      travellerMessageSequence: travellerMessageSequence,
      text: replacementText,
      clientCreatedAt: clientCreatedAt ?? DateTime.now(),
      expectedContextRevision: expectedContextRevision,
      deviceLocation: deviceLocation,
    );
  }

  factory ConversationTurnRequest.fromJson(Map<String, dynamic> json) {
    final operation = _requiredEnumByName(
      ConversationTurnOperation.values,
      _requiredString(json, 'operation'),
      fieldName: 'operation',
    );

    final rawDeviceLocation = _mapValue(json['deviceLocation']);

    return ConversationTurnRequest(
      requestId: _requiredString(json, 'requestId'),
      operation: operation,
      chatId: _requiredString(json, 'chatId'),
      travellerMessageId: _requiredString(json, 'travellerMessageId'),
      turnId: _requiredString(json, 'turnId'),
      travellerMessageSequence: _requiredInteger(
        json,
        'travellerMessageSequence',
      ),
      text: _requiredString(json, 'text'),
      clientCreatedAt: _requiredDateTime(json, 'clientCreatedAt'),
      expectedContextRevision: _requiredInteger(
        json,
        'expectedContextRevision',
      ),
      deviceLocation: rawDeviceLocation == null
          ? null
          : ConversationDeviceLocation.fromJson(rawDeviceLocation),
    );
  }

  /// Unique idempotency identifier for this network operation.
  final String requestId;

  final ConversationTurnOperation operation;

  /// Flutter creates the chat immediately after the traveller's first
  /// answer, then sends that Firestore chat identifier to FastAPI.
  final String chatId;

  /// For edits, this is the existing Firestore message document identifier.
  /// The backend replaces that message and removes all later messages.
  final String travellerMessageId;

  /// A fresh turn identifier is used for both new messages and edited
  /// messages so the regenerated assistant response belongs to this turn.
  final String turnId;

  /// The existing sequence is retained when editing a message. It allows
  /// later transcript messages to be removed while preserving earlier ones.
  final int travellerMessageSequence;

  final String text;
  final DateTime clientCreatedAt;

  /// Enables the backend to reject stale updates instead of merging a
  /// message against an older travel-context revision.
  final int expectedContextRevision;

  /// Included only when the traveller asks to use the device's current
  /// location. Manual location text is resolved and verified by FastAPI.
  final ConversationDeviceLocation? deviceLocation;

  bool get isEdit {
    return operation == ConversationTurnOperation.editMessage;
  }

  bool get hasDeviceLocation {
    return deviceLocation != null;
  }

  bool get isValid {
    try {
      _validate();
      return true;
    } on FormatException {
      return false;
    }
  }

  Map<String, dynamic> toJson() {
    return {
      'requestId': requestId,
      'operation': operation.name,
      'chatId': chatId,
      'travellerMessageId': travellerMessageId,
      'turnId': turnId,
      'travellerMessageSequence': travellerMessageSequence,
      'text': text.trim(),
      'clientCreatedAt': clientCreatedAt.toUtc().toIso8601String(),
      'expectedContextRevision': expectedContextRevision,
      'deviceLocation': deviceLocation?.toJson(),
    };
  }

  void _validate() {
    _validateIdentifier(requestId, fieldName: 'requestId');

    _validateIdentifier(travellerMessageId, fieldName: 'travellerMessageId');

    _validateIdentifier(turnId, fieldName: 'turnId');

    _validateIdentifier(chatId, fieldName: 'chatId');

    if (travellerMessageSequence < 0) {
      throw const FormatException(
        'travellerMessageSequence cannot be negative.',
      );
    }

    if (expectedContextRevision < 0) {
      throw const FormatException(
        'expectedContextRevision cannot be negative.',
      );
    }

    if (text.trim().isEmpty) {
      throw const FormatException('text cannot be empty.');
    }

    final location = deviceLocation;

    if (location != null && !location.isValid) {
      throw const FormatException('deviceLocation is invalid.');
    }
  }
}

String _requiredString(Map<String, dynamic> json, String fieldName) {
  final value = _stringValue(json[fieldName]);

  if (value == null) {
    throw FormatException('$fieldName must be a non-empty string.');
  }

  return value;
}

int _requiredInteger(Map<String, dynamic> json, String fieldName) {
  final value = _integerValue(json[fieldName]);

  if (value == null) {
    throw FormatException('$fieldName must be an integer.');
  }

  return value;
}

DateTime _requiredDateTime(Map<String, dynamic> json, String fieldName) {
  final value = _dateTimeValue(json[fieldName]);

  if (value == null) {
    throw FormatException('$fieldName must be a valid ISO-8601 date and time.');
  }

  return value;
}

String? _stringValue(dynamic value) {
  if (value is! String) {
    return null;
  }

  final normalizedValue = value.trim();

  return normalizedValue.isEmpty ? null : normalizedValue;
}

double? _doubleValue(dynamic value) {
  if (value is num && value.isFinite) {
    return value.toDouble();
  }

  return null;
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

DateTime? _dateTimeValue(dynamic value) {
  if (value is DateTime) {
    return value;
  }

  if (value is! String) {
    return null;
  }

  return DateTime.tryParse(value.trim());
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

T _requiredEnumByName<T extends Enum>(
  List<T> values,
  String name, {
  required String fieldName,
}) {
  for (final value in values) {
    if (value.name == name) {
      return value;
    }
  }

  throw FormatException('$fieldName contains an unsupported value: $name.');
}

void _validateIdentifier(String value, {required String fieldName}) {
  final normalizedValue = value.trim();

  if (normalizedValue.isEmpty || normalizedValue.contains('/')) {
    throw FormatException('$fieldName is invalid.');
  }
}
