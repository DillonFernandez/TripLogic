import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:trip_logic/models/recommendation_group.dart';

enum ConversationMessageAuthor { traveller, assistant }

enum ConversationMessageType {
  text,
  confirmation,
  recommendationGroup,
  itinerary,
  warning,
  error,
  loading,
}

enum ConversationMessageOrigin { client, backend }

enum ConversationMessageDeliveryStatus { pending, delivered, failed }

class ConversationMessage {
  ConversationMessage({
    required this.id,
    required this.turnId,
    required this.sequence,
    required this.author,
    required this.type,
    required this.origin,
    required this.text,
    required this.createdAt,
    this.editedAt,
    this.deliveryStatus = ConversationMessageDeliveryStatus.delivered,
    Map<String, dynamic> data = const <String, dynamic>{},
  }) : data = Map<String, dynamic>.unmodifiable(
         Map<String, dynamic>.from(data),
       );

  static const Object _unset = Object();

  factory ConversationMessage.travellerText({
    required String id,
    required String turnId,
    required int sequence,
    required String text,
    DateTime? createdAt,
    ConversationMessageDeliveryStatus deliveryStatus =
        ConversationMessageDeliveryStatus.pending,
  }) {
    return ConversationMessage(
      id: id,
      turnId: turnId,
      sequence: sequence,
      author: ConversationMessageAuthor.traveller,
      type: ConversationMessageType.text,
      origin: ConversationMessageOrigin.client,
      text: text.trim(),
      createdAt: createdAt ?? DateTime.now(),
      deliveryStatus: deliveryStatus,
    );
  }

  factory ConversationMessage.assistant({
    required String id,
    required String turnId,
    required int sequence,
    required ConversationMessageType type,
    required String text,
    DateTime? createdAt,
    ConversationMessageOrigin origin = ConversationMessageOrigin.backend,
    Map<String, dynamic> data = const <String, dynamic>{},
  }) {
    return ConversationMessage(
      id: id,
      turnId: turnId,
      sequence: sequence,
      author: ConversationMessageAuthor.assistant,
      type: type,
      origin: origin,
      text: text.trim(),
      createdAt: createdAt ?? DateTime.now(),
      data: data,
    );
  }

  factory ConversationMessage.loading({
    required String id,
    required String turnId,
    required int sequence,
    String text = 'Thinking...',
    DateTime? createdAt,
  }) {
    return ConversationMessage(
      id: id,
      turnId: turnId,
      sequence: sequence,
      author: ConversationMessageAuthor.assistant,
      type: ConversationMessageType.loading,
      origin: ConversationMessageOrigin.client,
      text: text.trim(),
      createdAt: createdAt ?? DateTime.now(),
    );
  }

  factory ConversationMessage.fromFirestore({
    required String id,
    required Map<String, dynamic> data,
  }) {
    final turnIdValue = data['turnId'];
    final sequenceValue = data['sequence'];
    final textValue = data['text'];

    if (id.trim().isEmpty || id.contains('/')) {
      throw const FormatException('The stored message identifier is invalid.');
    }

    if (turnIdValue is! String ||
        turnIdValue.trim().isEmpty ||
        turnIdValue.contains('/')) {
      throw const FormatException('The stored turn identifier is invalid.');
    }

    final sequence = _readStoredInteger(sequenceValue);

    if (sequence == null || sequence < 0) {
      throw const FormatException('The stored message sequence is invalid.');
    }

    if (textValue is! String || textValue.trim().isEmpty) {
      throw const FormatException('The stored message text is invalid.');
    }

    final author = _readStoredEnum(
      data['author'],
      ConversationMessageAuthor.values,
      ConversationMessageAuthor.assistant,
    );

    final type = _readStoredEnum(
      data['type'],
      ConversationMessageType.values,
      ConversationMessageType.text,
    );

    final defaultOrigin = author == ConversationMessageAuthor.traveller
        ? ConversationMessageOrigin.client
        : ConversationMessageOrigin.backend;

    final origin = _readStoredEnum(
      data['origin'],
      ConversationMessageOrigin.values,
      defaultOrigin,
    );

    final deliveryStatus = _readStoredEnum(
      data['deliveryStatus'],
      ConversationMessageDeliveryStatus.values,
      ConversationMessageDeliveryStatus.delivered,
    );

    final message = ConversationMessage(
      id: id.trim(),
      turnId: turnIdValue.trim(),
      sequence: sequence,
      author: author,
      type: type,
      origin: origin,
      text: textValue.trim(),
      createdAt: _readStoredDateTime(data['createdAt'], fieldName: 'createdAt'),
      editedAt: _readOptionalStoredDateTime(
        data['editedAt'],
        fieldName: 'editedAt',
      ),
      deliveryStatus: deliveryStatus,
      data: _mapValue(data['data']) ?? const <String, dynamic>{},
    );

    if (!message.isValid) {
      throw const FormatException(
        'The stored conversation message is invalid.',
      );
    }

    return message;
  }

  final String id;

  /// Groups the traveller message and its related assistant response.
  final String turnId;

  /// Provides stable transcript ordering and supports deleting all messages
  /// after an edited traveller message.
  final int sequence;

  final ConversationMessageAuthor author;
  final ConversationMessageType type;
  final ConversationMessageOrigin origin;

  final String text;
  final DateTime createdAt;
  final DateTime? editedAt;

  final ConversationMessageDeliveryStatus deliveryStatus;

  /// Flexible payload for confirmation summaries, recommendation groups,
  /// itineraries, warnings, attributions, routes, and other backend results.
  final Map<String, dynamic> data;

  bool get isFromTraveller {
    return author == ConversationMessageAuthor.traveller;
  }

  bool get isFromAssistant {
    return author == ConversationMessageAuthor.assistant;
  }

  bool get isEdited {
    return editedAt != null;
  }

  bool get isPending {
    return deliveryStatus == ConversationMessageDeliveryStatus.pending;
  }

  bool get hasFailed {
    return deliveryStatus == ConversationMessageDeliveryStatus.failed;
  }

  bool get isTrustedBackendMessage {
    return origin == ConversationMessageOrigin.backend;
  }

  bool get canEdit {
    return isFromTraveller && type == ConversationMessageType.text;
  }

  bool get hasData {
    return data.isNotEmpty;
  }

  List<RecommendationGroup> get recommendationGroups {
    final rawGroups = data['recommendationGroups'];

    if (rawGroups is! List) {
      return const <RecommendationGroup>[];
    }

    final groups = <RecommendationGroup>[];

    for (final rawGroup in rawGroups) {
      final groupMap = _mapValue(rawGroup);

      if (groupMap == null) {
        continue;
      }

      try {
        final group = RecommendationGroup.fromJson(groupMap);

        if (group.isValid) {
          groups.add(group);
        }
      } on FormatException {
        continue;
      }
    }

    return List<RecommendationGroup>.unmodifiable(groups);
  }

  bool get hasRecommendationGroups {
    return recommendationGroups.isNotEmpty;
  }

  bool get isValid {
    return id.trim().isNotEmpty &&
        !id.contains('/') &&
        turnId.trim().isNotEmpty &&
        !turnId.contains('/') &&
        sequence >= 0 &&
        text.trim().isNotEmpty;
  }

  ConversationMessage replaceTravellerText(
    String replacement, {
    DateTime? replacementTime,
  }) {
    if (!canEdit) {
      throw StateError('Only traveller text messages can be edited.');
    }

    final normalizedReplacement = replacement.trim();

    if (normalizedReplacement.isEmpty) {
      throw ArgumentError.value(
        replacement,
        'replacement',
        'The replacement message cannot be empty.',
      );
    }

    return copyWith(
      text: normalizedReplacement,
      editedAt: replacementTime ?? DateTime.now(),
      deliveryStatus: ConversationMessageDeliveryStatus.pending,
    );
  }

  ConversationMessage copyWith({
    String? id,
    String? turnId,
    int? sequence,
    ConversationMessageAuthor? author,
    ConversationMessageType? type,
    ConversationMessageOrigin? origin,
    String? text,
    DateTime? createdAt,
    Object? editedAt = _unset,
    ConversationMessageDeliveryStatus? deliveryStatus,
    Map<String, dynamic>? data,
  }) {
    return ConversationMessage(
      id: id ?? this.id,
      turnId: turnId ?? this.turnId,
      sequence: sequence ?? this.sequence,
      author: author ?? this.author,
      type: type ?? this.type,
      origin: origin ?? this.origin,
      text: text ?? this.text,
      createdAt: createdAt ?? this.createdAt,
      editedAt: identical(editedAt, _unset)
          ? this.editedAt
          : editedAt as DateTime?,
      deliveryStatus: deliveryStatus ?? this.deliveryStatus,
      data: data ?? this.data,
    );
  }
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

int? _readStoredInteger(dynamic value) {
  if (value is int) {
    return value;
  }

  if (value is num && value.isFinite && value == value.toInt()) {
    return value.toInt();
  }

  return null;
}

T _readStoredEnum<T extends Enum>(
  dynamic value,
  List<T> supportedValues,
  T fallback,
) {
  if (value is! String) {
    return fallback;
  }

  for (final supportedValue in supportedValues) {
    if (supportedValue.name == value.trim()) {
      return supportedValue;
    }
  }

  return fallback;
}

DateTime _readStoredDateTime(dynamic value, {required String fieldName}) {
  if (value is Timestamp) {
    return value.toDate();
  }

  if (value is DateTime) {
    return value;
  }

  if (value is String) {
    final parsedValue = DateTime.tryParse(value);

    if (parsedValue != null) {
      return parsedValue;
    }
  }

  throw FormatException('The stored $fieldName value is invalid.');
}

DateTime? _readOptionalStoredDateTime(
  dynamic value, {
  required String fieldName,
}) {
  if (value == null) {
    return null;
  }

  return _readStoredDateTime(value, fieldName: fieldName);
}
