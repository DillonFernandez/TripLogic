import 'package:trip_logic/models/conversation_message.dart';
import 'package:trip_logic/models/travel_context.dart';

enum ConversationNextAction {
  askQuestion,
  requestConfirmation,
  requestPlaceSelection,
  resolveRouteWarning,
  askModifyOrNewTrip,
  none,
}

class ConversationTurnResponse {
  ConversationTurnResponse({
    required this.requestId,
    required this.chatId,
    required this.turnId,
    required this.acceptedTravellerMessageId,
    required this.contextRevision,
    required this.nextAction,
    required this.context,
    required List<ConversationMessage> assistantMessages,
    required this.createdAt,
    this.suggestedChatTitle,
    Map<String, dynamic> metadata = const <String, dynamic>{},
  }) : assistantMessages = List<ConversationMessage>.unmodifiable(
         _sortedMessages(assistantMessages),
       ),
       metadata = Map<String, dynamic>.unmodifiable(
         Map<String, dynamic>.from(metadata),
       ) {
    _validate();
  }

  factory ConversationTurnResponse.fromJson(Map<String, dynamic> json) {
    final requestId = _requiredString(json, 'requestId');

    final chatId = _requiredString(json, 'chatId');

    final turnId = _requiredString(json, 'turnId');

    final acceptedTravellerMessageId = _requiredString(
      json,
      'acceptedTravellerMessageId',
    );

    final contextRevision = _requiredInteger(json, 'contextRevision');

    final nextAction = _requiredEnumByName(
      ConversationNextAction.values,
      _requiredString(json, 'nextAction'),
      fieldName: 'nextAction',
    );

    final createdAt = _requiredDateTime(json, 'createdAt');

    final contextMap = _requiredMap(json, 'context');

    final rawAssistantMessages = json['assistantMessages'];

    if (rawAssistantMessages is! List || rawAssistantMessages.isEmpty) {
      throw const FormatException(
        'assistantMessages must contain at least one message.',
      );
    }

    final assistantMessages = <ConversationMessage>[];

    for (final rawMessage in rawAssistantMessages) {
      final messageMap = _mapValue(rawMessage);

      if (messageMap == null) {
        throw const FormatException(
          'Each assistant message must be a JSON object.',
        );
      }

      assistantMessages.add(
        _assistantMessageFromJson(
          messageMap,
          turnId: turnId,
          fallbackCreatedAt: createdAt,
        ),
      );
    }

    return ConversationTurnResponse(
      requestId: requestId,
      chatId: chatId,
      turnId: turnId,
      acceptedTravellerMessageId: acceptedTravellerMessageId,
      contextRevision: contextRevision,
      nextAction: nextAction,
      context: TravelContext.fromJson(contextMap),
      assistantMessages: assistantMessages,
      createdAt: createdAt,
      suggestedChatTitle: _stringValue(json['suggestedChatTitle']),
      metadata: _mapValue(json['metadata']) ?? const <String, dynamic>{},
    );
  }

  final String requestId;
  final String chatId;
  final String turnId;

  /// Identifies the local traveller message that the backend accepted.
  /// Flutter can use this to change its delivery status from pending
  /// to delivered.
  final String acceptedTravellerMessageId;

  /// Must increase whenever the backend changes the structured context.
  final int contextRevision;

  /// Describes what the traveller is expected to do next. The wording of
  /// the actual question remains inside the assistant message.
  final ConversationNextAction nextAction;

  /// The validated and merged context returned by FastAPI.
  final TravelContext context;

  /// One response may include several transcript items, such as a warning
  /// followed by a question or several recommendation groups.
  final List<ConversationMessage> assistantMessages;

  /// The backend may suggest a title after the first completed request.
  /// The client must not replace a manually renamed title.
  final String? suggestedChatTitle;

  final DateTime createdAt;

  /// Optional trace, diagnostics, provider attribution, or pagination data.
  final Map<String, dynamic> metadata;

  ConversationMessage get primaryMessage {
    return assistantMessages.first;
  }

  bool get requiresTravellerInput {
    return nextAction != ConversationNextAction.none;
  }

  bool get hasRecommendations {
    return assistantMessages.any(
      (message) =>
          message.type == ConversationMessageType.recommendationGroup ||
          message.hasRecommendationGroups,
    );
  }

  bool get hasItinerary {
    return assistantMessages.any(
      (message) => message.type == ConversationMessageType.itinerary,
    );
  }

  bool get hasWarning {
    return assistantMessages.any(
      (message) => message.type == ConversationMessageType.warning,
    );
  }

  bool get requestsConfirmation {
    return nextAction == ConversationNextAction.requestConfirmation;
  }

  bool get requestsPlaceSelection {
    return nextAction == ConversationNextAction.requestPlaceSelection;
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
      'chatId': chatId,
      'turnId': turnId,
      'acceptedTravellerMessageId': acceptedTravellerMessageId,
      'contextRevision': contextRevision,
      'nextAction': nextAction.name,
      'context': context.toJson(),
      'assistantMessages': assistantMessages
          .map(_assistantMessageToJson)
          .toList(),
      'suggestedChatTitle': suggestedChatTitle,
      'createdAt': createdAt.toUtc().toIso8601String(),
      'metadata': metadata,
    };
  }

  void _validate() {
    _validateIdentifier(requestId, fieldName: 'requestId');

    _validateIdentifier(chatId, fieldName: 'chatId');

    _validateIdentifier(turnId, fieldName: 'turnId');

    _validateIdentifier(
      acceptedTravellerMessageId,
      fieldName: 'acceptedTravellerMessageId',
    );

    if (contextRevision < 0) {
      throw const FormatException('contextRevision cannot be negative.');
    }

    if (context.revision != contextRevision) {
      throw const FormatException(
        'context.revision must match contextRevision.',
      );
    }

    if (assistantMessages.isEmpty) {
      throw const FormatException(
        'At least one assistant message is required.',
      );
    }

    final messageIds = <String>{};
    final sequences = <int>{};

    for (final message in assistantMessages) {
      if (!message.isValid) {
        throw const FormatException('An assistant message is invalid.');
      }

      if (!message.isFromAssistant || !message.isTrustedBackendMessage) {
        throw const FormatException(
          'All returned messages must be trusted assistant messages.',
        );
      }

      if (message.turnId != turnId) {
        throw const FormatException(
          'Every assistant message must use the response turnId.',
        );
      }

      if (!messageIds.add(message.id)) {
        throw const FormatException(
          'Assistant message identifiers must be unique.',
        );
      }

      if (!sequences.add(message.sequence)) {
        throw const FormatException(
          'Assistant message sequence values must be unique.',
        );
      }
    }

    final title = suggestedChatTitle;

    if (title != null && (title.trim().isEmpty || title.trim().length > 100)) {
      throw const FormatException(
        'suggestedChatTitle must contain 1 to 100 characters.',
      );
    }
  }
}

ConversationMessage _assistantMessageFromJson(
  Map<String, dynamic> json, {
  required String turnId,
  required DateTime fallbackCreatedAt,
}) {
  final messageId = _requiredString(json, 'id');

  final sequence = _requiredInteger(json, 'sequence');

  final type = _requiredEnumByName(
    ConversationMessageType.values,
    _requiredString(json, 'type'),
    fieldName: 'assistantMessages.type',
  );

  final text = _requiredString(json, 'text');

  final messageCreatedAt =
      _dateTimeValue(json['createdAt']) ?? fallbackCreatedAt;

  return ConversationMessage.assistant(
    id: messageId,
    turnId: turnId,
    sequence: sequence,
    type: type,
    text: text,
    createdAt: messageCreatedAt,
    data: _mapValue(json['data']) ?? const <String, dynamic>{},
  );
}

Map<String, dynamic> _assistantMessageToJson(ConversationMessage message) {
  return {
    'id': message.id,
    'sequence': message.sequence,
    'type': message.type.name,
    'text': message.text,
    'createdAt': message.createdAt.toUtc().toIso8601String(),
    'data': message.data,
  };
}

List<ConversationMessage> _sortedMessages(List<ConversationMessage> messages) {
  final sortedMessages = List<ConversationMessage>.from(messages);

  sortedMessages.sort(
    (first, second) => first.sequence.compareTo(second.sequence),
  );

  return sortedMessages;
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

Map<String, dynamic> _requiredMap(Map<String, dynamic> json, String fieldName) {
  final value = _mapValue(json[fieldName]);

  if (value == null) {
    throw FormatException('$fieldName must be a JSON object.');
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
