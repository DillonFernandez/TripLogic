import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:trip_logic/models/conversation_message.dart';
import 'package:trip_logic/models/conversation_turn_request.dart';

class ConversationStoreException implements Exception {
  const ConversationStoreException(this.message);

  final String message;

  @override
  String toString() => message;
}

class PreparedConversationTurn {
  const PreparedConversationTurn({
    required this.requestId,
    required this.chatId,
    required this.turnId,
    required this.travellerMessageId,
    required this.travellerMessageSequence,
    required this.expectedContextRevision,
    required this.text,
    required this.clientCreatedAt,
  });

  final String requestId;
  final String chatId;
  final String turnId;
  final String travellerMessageId;
  final int travellerMessageSequence;
  final int expectedContextRevision;
  final String text;
  final DateTime clientCreatedAt;

  ConversationTurnRequest toRequest({
    ConversationDeviceLocation? deviceLocation,
  }) {
    return ConversationTurnRequest.newMessage(
      requestId: requestId,
      chatId: chatId,
      travellerMessageId: travellerMessageId,
      turnId: turnId,
      travellerMessageSequence: travellerMessageSequence,
      text: text,
      expectedContextRevision: expectedContextRevision,
      clientCreatedAt: clientCreatedAt,
      deviceLocation: deviceLocation,
    );
  }
}

class StoredConversationSummary {
  const StoredConversationSummary({
    required this.id,
    required this.title,
    required this.pinned,
    required this.contextRevision,
    required this.lastSequence,
    required this.lastMessageText,
    required this.updatedAt,
  });

  final String id;
  final String title;
  final bool pinned;
  final int contextRevision;
  final int lastSequence;
  final String lastMessageText;
  final DateTime updatedAt;

  factory StoredConversationSummary.fromDocument(
    QueryDocumentSnapshot<Map<String, dynamic>> document,
  ) {
    final data = document.data();

    final storedTitle = data['title'];
    final storedLastMessage = data['lastMessageText'];

    return StoredConversationSummary(
      id: document.id,
      title: storedTitle is String && storedTitle.trim().isNotEmpty
          ? storedTitle.trim()
          : 'New trip',
      pinned: data['pinned'] == true,
      contextRevision: _readNonNegativeInteger(
        data['contextRevision'],
        fieldName: 'contextRevision',
        fallback: 0,
      ),
      lastSequence: _readInteger(
        data['lastSequence'],
        fieldName: 'lastSequence',
        fallback: -1,
        minimum: -1,
      ),
      lastMessageText: storedLastMessage is String
          ? storedLastMessage.trim()
          : '',
      updatedAt: _readFirestoreDateTime(data['updatedAt']),
    );
  }
}

class ConversationStoreService {
  ConversationStoreService({FirebaseFirestore? firestore})
    : _firestore = firestore ?? FirebaseFirestore.instance;

  final FirebaseFirestore _firestore;

  Stream<List<StoredConversationSummary>> watchChats({required String uid}) {
    final normalizedUid = uid.trim();

    if (normalizedUid.isEmpty) {
      return Stream<List<StoredConversationSummary>>.error(
        const ConversationStoreException('A signed-in traveller is required.'),
      );
    }

    return _firestore
        .collection('users')
        .doc(normalizedUid)
        .collection('chats')
        .orderBy('updatedAt', descending: true)
        .snapshots()
        .map((snapshot) {
          final chats = snapshot.docs
              .map(StoredConversationSummary.fromDocument)
              .toList();

          chats.sort((first, second) {
            if (first.pinned && !second.pinned) {
              return -1;
            }

            if (!first.pinned && second.pinned) {
              return 1;
            }

            return second.updatedAt.compareTo(first.updatedAt);
          });

          return chats;
        });
  }

  Future<List<ConversationMessage>> loadMessages({
    required String uid,
    required String chatId,
  }) async {
    final normalizedUid = uid.trim();
    final normalizedChatId = chatId.trim();

    if (normalizedUid.isEmpty) {
      throw const ConversationStoreException(
        'A signed-in traveller is required.',
      );
    }

    if (normalizedChatId.isEmpty || normalizedChatId.contains('/')) {
      throw const ConversationStoreException(
        'The conversation identifier is invalid.',
      );
    }

    try {
      final snapshot = await _firestore
          .collection('users')
          .doc(normalizedUid)
          .collection('chats')
          .doc(normalizedChatId)
          .collection('messages')
          .orderBy('sequence')
          .get();

      final messages = <ConversationMessage>[];

      for (final document in snapshot.docs) {
        try {
          messages.add(
            ConversationMessage.fromFirestore(
              id: document.id,
              data: document.data(),
            ),
          );
        } on FormatException catch (error) {
          throw ConversationStoreException(
            'A stored conversation message is invalid: '
            '${error.message}',
          );
        }
      }

      return List<ConversationMessage>.unmodifiable(messages);
    } on ConversationStoreException {
      rethrow;
    } on FirebaseException catch (error) {
      throw ConversationStoreException(
        error.message ?? 'Unable to load the conversation messages.',
      );
    }
  }

  Future<void> updateChatTitle({
    required String uid,
    required String chatId,
    required String title,
  }) async {
    final normalizedUid = uid.trim();
    final normalizedChatId = chatId.trim();
    final normalizedTitle = title.trim();

    if (normalizedUid.isEmpty) {
      throw const ConversationStoreException(
        'A signed-in traveller is required.',
      );
    }

    if (normalizedChatId.isEmpty || normalizedChatId.contains('/')) {
      throw const ConversationStoreException(
        'The conversation identifier is invalid.',
      );
    }

    if (normalizedTitle.isEmpty) {
      throw const ConversationStoreException(
        'The conversation title cannot be empty.',
      );
    }

    try {
      await _firestore
          .collection('users')
          .doc(normalizedUid)
          .collection('chats')
          .doc(normalizedChatId)
          .update({
            'title': normalizedTitle,
            'updatedAt': Timestamp.fromDate(DateTime.now().toUtc()),
          });
    } on FirebaseException catch (error) {
      throw ConversationStoreException(
        error.message ?? 'Unable to rename the conversation.',
      );
    }
  }

  Future<void> setChatPinned({
    required String uid,
    required String chatId,
    required bool pinned,
  }) async {
    final normalizedUid = uid.trim();
    final normalizedChatId = chatId.trim();

    if (normalizedUid.isEmpty) {
      throw const ConversationStoreException(
        'A signed-in traveller is required.',
      );
    }

    if (normalizedChatId.isEmpty || normalizedChatId.contains('/')) {
      throw const ConversationStoreException(
        'The conversation identifier is invalid.',
      );
    }

    try {
      await _firestore
          .collection('users')
          .doc(normalizedUid)
          .collection('chats')
          .doc(normalizedChatId)
          .update({
            'pinned': pinned,
            'updatedAt': Timestamp.fromDate(DateTime.now().toUtc()),
          });
    } on FirebaseException catch (error) {
      throw ConversationStoreException(
        error.message ?? 'Unable to update the conversation pin.',
      );
    }
  }

  Future<void> deleteChat({required String uid, required String chatId}) async {
    final normalizedUid = uid.trim();
    final normalizedChatId = chatId.trim();

    if (normalizedUid.isEmpty) {
      throw const ConversationStoreException(
        'A signed-in traveller is required.',
      );
    }

    if (normalizedChatId.isEmpty || normalizedChatId.contains('/')) {
      throw const ConversationStoreException(
        'The conversation identifier is invalid.',
      );
    }

    final chatReference = _firestore
        .collection('users')
        .doc(normalizedUid)
        .collection('chats')
        .doc(normalizedChatId);

    try {
      await _deleteCollectionDocuments(chatReference.collection('messages'));

      await _deleteCollectionDocuments(chatReference.collection('requests'));

      await chatReference.delete();
    } on FirebaseException catch (error) {
      throw ConversationStoreException(
        error.message ?? 'Unable to delete the conversation.',
      );
    }
  }

  Future<void> _deleteCollectionDocuments(
    CollectionReference<Map<String, dynamic>> collection,
  ) async {
    while (true) {
      final snapshot = await collection.limit(400).get();

      if (snapshot.docs.isEmpty) {
        return;
      }

      final batch = _firestore.batch();

      for (final document in snapshot.docs) {
        batch.delete(document.reference);
      }

      await batch.commit();
    }
  }

  Future<PreparedConversationTurn> prepareTravellerMessage({
    required String uid,
    required String text,
    String? chatId,
    String initialTitle = 'New trip',
  }) async {
    final normalizedUid = uid.trim();
    final normalizedText = text.trim();
    final normalizedChatId = chatId?.trim();
    final normalizedTitle = initialTitle.trim();

    if (normalizedUid.isEmpty) {
      throw const ConversationStoreException(
        'A signed-in traveller is required.',
      );
    }

    if (normalizedText.isEmpty) {
      throw const ConversationStoreException(
        'The traveller message cannot be empty.',
      );
    }

    if (normalizedChatId?.contains('/') == true) {
      throw const ConversationStoreException(
        'The conversation identifier is invalid.',
      );
    }

    final isNewChat = normalizedChatId == null || normalizedChatId.isEmpty;

    final chatsReference = _firestore
        .collection('users')
        .doc(normalizedUid)
        .collection('chats');

    final chatReference = isNewChat
        ? chatsReference.doc()
        : chatsReference.doc(normalizedChatId);

    final messageReference = chatReference.collection('messages').doc();

    final requestId = chatReference.collection('requests').doc().id;

    final turnId = 'turn_${messageReference.id}';

    final createdAt = DateTime.now().toUtc();
    final firestoreCreatedAt = Timestamp.fromDate(createdAt);

    try {
      return await _firestore.runTransaction<PreparedConversationTurn>((
        transaction,
      ) async {
        final chatSnapshot = await transaction.get(chatReference);

        var contextRevision = 0;
        var lastSequence = -1;

        if (chatSnapshot.exists) {
          final chatData = chatSnapshot.data() ?? const <String, dynamic>{};

          final storedUid = chatData['uid'];

          if (storedUid is String &&
              storedUid.trim().isNotEmpty &&
              storedUid != normalizedUid) {
            throw const ConversationStoreException(
              'You do not have access to this conversation.',
            );
          }

          contextRevision = _readNonNegativeInteger(
            chatData['contextRevision'],
            fieldName: 'contextRevision',
            fallback: 0,
          );

          lastSequence = _readInteger(
            chatData['lastSequence'],
            fieldName: 'lastSequence',
            fallback: -1,
            minimum: -1,
          );
        } else if (!isNewChat) {
          throw const ConversationStoreException(
            'The selected conversation no longer exists.',
          );
        }

        final travellerSequence = lastSequence + 1;

        final chatUpdate = <String, dynamic>{
          'uid': normalizedUid,
          'lastMessageText': normalizedText,
          'lastMessageAt': firestoreCreatedAt,
          'lastSequence': travellerSequence,
          'lastTurnId': turnId,
          'updatedAt': firestoreCreatedAt,
        };

        if (isNewChat) {
          transaction.set(chatReference, {
            ...chatUpdate,
            'title': normalizedTitle.isEmpty ? 'New trip' : normalizedTitle,
            'pinned': false,
            'contextRevision': 0,
            'travelContext': null,
            'nextAction': 'none',
            'createdAt': firestoreCreatedAt,
          });
        } else {
          transaction.update(chatReference, chatUpdate);
        }

        transaction.set(messageReference, {
          'turnId': turnId,
          'sequence': travellerSequence,
          'author': 'traveller',
          'type': 'text',
          'origin': 'client',
          'text': normalizedText,
          'createdAt': firestoreCreatedAt,
          'editedAt': null,
          'deliveryStatus': 'pending',
          'data': const <String, dynamic>{},
          'contextRevision': contextRevision,
        });

        return PreparedConversationTurn(
          requestId: requestId,
          chatId: chatReference.id,
          turnId: turnId,
          travellerMessageId: messageReference.id,
          travellerMessageSequence: travellerSequence,
          expectedContextRevision: contextRevision,
          text: normalizedText,
          clientCreatedAt: createdAt,
        );
      });
    } on ConversationStoreException {
      rethrow;
    } on FirebaseException catch (error) {
      throw ConversationStoreException(
        error.message ?? 'Unable to prepare the conversation message.',
      );
    }
  }
}

int _readNonNegativeInteger(
  dynamic value, {
  required String fieldName,
  required int fallback,
}) {
  return _readInteger(
    value,
    fieldName: fieldName,
    fallback: fallback,
    minimum: 0,
  );
}

int _readInteger(
  dynamic value, {
  required String fieldName,
  required int fallback,
  required int minimum,
}) {
  if (value == null) {
    return fallback;
  }

  int? result;

  if (value is int) {
    result = value;
  } else if (value is num && value.isFinite && value == value.toInt()) {
    result = value.toInt();
  }

  if (result == null || result < minimum) {
    throw ConversationStoreException('The stored $fieldName value is invalid.');
  }

  return result;
}

DateTime _readFirestoreDateTime(dynamic value) {
  if (value is Timestamp) {
    return value.toDate().toUtc();
  }

  if (value is DateTime) {
    return value.toUtc();
  }

  return DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
}
