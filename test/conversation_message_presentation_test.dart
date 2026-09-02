import 'package:flutter_test/flutter_test.dart';
import 'package:trip_logic/models/conversation_message.dart';
import 'package:trip_logic/pages/main/home.dart';

void main() {
  ConversationMessage assistantMessage({
    required ConversationMessageType type,
    required String text,
    Map<String, dynamic> data = const <String, dynamic>{},
  }) {
    return ConversationMessage.assistant(
      id: 'assistant-message',
      turnId: 'turn-id',
      sequence: 1,
      type: type,
      text: text,
      data: data,
    );
  }

  Map<String, dynamic> recommendationData() {
    return <String, dynamic>{
      'recommendationGroups': <Map<String, dynamic>>[
        <String, dynamic>{
          'requestGroupId': 'restaurant-request',
          'recommendationType': 'restaurant',
          'required': true,
          'result': <String, dynamic>{
            'recommendationType': 'restaurant',
            'count': 1,
            'topRecommendations': <Map<String, dynamic>>[
              <String, dynamic>{
                'id': 'provider-place',
                'name': 'Provider Place',
              },
            ],
            'moreRecommendations': <Map<String, dynamic>>[],
          },
        },
      ],
    };
  }

  test('filler text is hidden when recommendation groups are present', () {
    final message = assistantMessage(
      type: ConversationMessageType.text,
      text: 'Your trip details are confirmed. Your recommendations are ready.',
      data: recommendationData(),
    );

    expect(message.hasRecommendationGroups, isTrue);
    expect(shouldRenderConversationMessageText(message), isFalse);
  });

  test('ordinary assistant text remains visible', () {
    final message = assistantMessage(
      type: ConversationMessageType.text,
      text: 'How can I help?',
    );

    expect(shouldRenderConversationMessageText(message), isTrue);
  });

  test('confirmation summaries remain visible', () {
    final message = assistantMessage(
      type: ConversationMessageType.confirmation,
      text: 'Please confirm these trip details.',
    );

    expect(shouldRenderConversationMessageText(message), isTrue);
  });

  test('errors remain visible', () {
    final message = assistantMessage(
      type: ConversationMessageType.error,
      text: 'The request could not be completed.',
    );

    expect(shouldRenderConversationMessageText(message), isTrue);
  });
}
