import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:trip_logic/models/conversation_message.dart';
import 'package:trip_logic/pages/main/profile.dart';
import 'package:trip_logic/services/api_service.dart';
import 'package:trip_logic/services/conversation_store_service.dart';
import 'package:trip_logic/theme/app_colors.dart';
import 'package:trip_logic/widgets/recommendation_group_view.dart';

bool shouldRenderConversationMessageText(ConversationMessage message) {
  return !message.hasRecommendationGroups;
}

class _ChatEntry {
  _ChatEntry(this.title)
    : id = null,
      contextRevision = 0,
      pinned = false,
      messages = <ConversationMessage>[];

  String title;
  String? id;
  int contextRevision;
  bool pinned;
  final List<ConversationMessage> messages;
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();
  final List<_ChatEntry> _chatHistory = [_ChatEntry('New chat')];
  int _selectedChatIndex = 0;
  late final ApiService _apiService;
  late final ConversationStoreService _conversationStoreService;
  StreamSubscription<List<StoredConversationSummary>>? _chatSubscription;
  bool _isSendingMessage = false;
  late final ScrollController _scrollController;
  late final TextEditingController _messageController;
  bool _hasScrolled = false;
  Timer? _drawerFeedbackTimer;
  String? _drawerFeedbackMessage;
  Color? _drawerFeedbackColor;
  IconData? _drawerFeedbackIcon;

  @override
  void initState() {
    super.initState();

    _apiService = ApiService();
    _conversationStoreService = ConversationStoreService();

    _scrollController = ScrollController()..addListener(_handleScroll);
    _messageController = TextEditingController();

    _startWatchingChats();
  }

  @override
  void dispose() {
    _chatSubscription?.cancel();
    _drawerFeedbackTimer?.cancel();
    _apiService.close();

    _scrollController.removeListener(_handleScroll);
    _scrollController.dispose();
    _messageController.dispose();
    super.dispose();
  }

  void _startWatchingChats() {
    final user = FirebaseAuth.instance.currentUser;

    if (user == null) {
      return;
    }

    _chatSubscription = _conversationStoreService
        .watchChats(uid: user.uid)
        .listen(
          _applyStoredChats,
          onError: (Object error, StackTrace stackTrace) {
            debugPrint('Unable to watch saved chats: $error');
            debugPrintStack(stackTrace: stackTrace);
          },
        );
  }

  void _applyStoredChats(List<StoredConversationSummary> storedChats) {
    if (!mounted) {
      return;
    }

    final currentlySelectedEntry = _selectedChat;
    final currentlySelectedId = currentlySelectedEntry.id;

    final existingEntriesById = <String, _ChatEntry>{
      for (final entry in _chatHistory)
        if (entry.id != null) entry.id!: entry,
    };

    final unsavedChats = _chatHistory
        .where((entry) => entry.id == null)
        .toList();

    final mergedEntries = <_ChatEntry>[];

    for (final storedChat in storedChats) {
      var entry = existingEntriesById[storedChat.id];

      if (entry == null) {
        final matchingUnsavedIndex = unsavedChats.indexWhere((candidate) {
          final lastLocalMessage = candidate.messages.isEmpty
              ? ''
              : candidate.messages.last.text.trim();

          return candidate.title.trim() == storedChat.title.trim() &&
              (lastLocalMessage.isEmpty ||
                  lastLocalMessage == storedChat.lastMessageText);
        });

        if (matchingUnsavedIndex >= 0) {
          entry = unsavedChats.removeAt(matchingUnsavedIndex);
        } else {
          entry = _ChatEntry(storedChat.title);
        }
      }

      entry
        ..id = storedChat.id
        ..title = storedChat.title
        ..pinned = storedChat.pinned
        ..contextRevision = storedChat.contextRevision;

      mergedEntries.add(entry);
    }

    mergedEntries.addAll(unsavedChats);

    if (mergedEntries.isEmpty) {
      mergedEntries.add(_ChatEntry('New chat'));
    }

    var newSelectedIndex = -1;

    if (currentlySelectedId != null) {
      newSelectedIndex = mergedEntries.indexWhere(
        (entry) => entry.id == currentlySelectedId,
      );
    } else {
      newSelectedIndex = mergedEntries.indexOf(currentlySelectedEntry);
    }

    if (newSelectedIndex < 0) {
      newSelectedIndex = 0;
    }

    setState(() {
      _chatHistory
        ..clear()
        ..addAll(mergedEntries);

      _selectedChatIndex = newSelectedIndex;
    });
  }

  void _handleScroll() {
    final scrolled =
        _scrollController.hasClients && _scrollController.offset > 0;
    if (scrolled == _hasScrolled) return;
    setState(() {
      _hasScrolled = scrolled;
    });
  }

  void _scrollToLatestMessage() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) {
        return;
      }

      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }

  void _openProfile() {
    Navigator.of(context).push<void>(
      PageRouteBuilder(
        pageBuilder: (_, _, _) => const ProfilePage(),
        transitionDuration: Duration.zero,
        reverseTransitionDuration: Duration.zero,
        opaque: true,
      ),
    );
  }

  void _openSearch() async {
    final selectedChat = await Navigator.of(context).push<String?>(
      MaterialPageRoute(
        builder: (_) => ChatSearchPage(
          chatHistory: _chatHistory
              .where(_hasMeaningfulChatTitle)
              .map((entry) => entry.title)
              .toList(),
          selectedChat: _hasMeaningfulChatTitle(_selectedChat)
              ? _selectedChat.title
              : '',
        ),
      ),
    );

    if (selectedChat == null) {
      return;
    }

    final selectedIndex = _chatHistory.indexWhere(
      (entry) => entry.title == selectedChat,
    );
    if (selectedIndex != -1) {
      setState(() {
        _selectedChatIndex = selectedIndex;
      });
    }
  }

  void _openMenu() {
    _scaffoldKey.currentState?.openDrawer();
  }

  bool _hasMeaningfulChatTitle(_ChatEntry entry) {
    final title = entry.title.trim().toLowerCase();

    return title.isNotEmpty &&
        title != 'new chat' &&
        title != 'new trip' &&
        !title.startsWith('new chat ') &&
        !title.startsWith('new trip ');
  }

  _ChatEntry get _selectedChat {
    return _chatHistory[_selectedChatIndex];
  }

  List<ConversationMessage> get _selectedMessages {
    return _selectedChat.messages;
  }

  bool get _canSendMessage {
    return !_isSendingMessage && _messageController.text.trim().isNotEmpty;
  }

  Future<void> _handleSendPressed() async {
    if (!_canSendMessage) {
      return;
    }

    final user = FirebaseAuth.instance.currentUser;

    if (user == null) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(
          const SnackBar(
            content: Text('Please sign in before sending a message.'),
            behavior: SnackBarBehavior.floating,
          ),
        );

      return;
    }

    final messageText = _messageController.text.trim();
    final selectedChat = _selectedChat;

    PreparedConversationTurn? preparedTurn;
    ConversationMessage? loadingMessage;

    setState(() {
      _isSendingMessage = true;
      _messageController.clear();
    });

    try {
      preparedTurn = await _conversationStoreService.prepareTravellerMessage(
        uid: user.uid,
        text: messageText,
        chatId: selectedChat.id,
        initialTitle: selectedChat.title,
      );

      final travellerMessage = ConversationMessage.travellerText(
        id: preparedTurn.travellerMessageId,
        turnId: preparedTurn.turnId,
        sequence: preparedTurn.travellerMessageSequence,
        text: preparedTurn.text,
        createdAt: preparedTurn.clientCreatedAt,
      );

      if (!mounted) {
        return;
      }

      loadingMessage = ConversationMessage.loading(
        id: 'loading_${preparedTurn.travellerMessageId}',
        turnId: preparedTurn.turnId,
        sequence: preparedTurn.travellerMessageSequence + 1,
        text: 'Thinking...',
      );

      setState(() {
        selectedChat.id = preparedTurn!.chatId;
        selectedChat.messages
          ..add(travellerMessage)
          ..add(loadingMessage!);
      });

      _scrollToLatestMessage();

      final response = await _apiService.processConversationTurn(
        preparedTurn.toRequest(),
      );

      if (!mounted) {
        return;
      }

      setState(() {
        selectedChat.messages.removeWhere(
          (message) => message.id == loadingMessage?.id,
        );

        final travellerIndex = selectedChat.messages.indexWhere(
          (message) => message.id == preparedTurn!.travellerMessageId,
        );

        if (travellerIndex != -1) {
          selectedChat.messages[travellerIndex] = selectedChat
              .messages[travellerIndex]
              .copyWith(
                deliveryStatus: ConversationMessageDeliveryStatus.delivered,
              );
        }

        selectedChat.contextRevision = response.contextRevision;
        selectedChat.messages.addAll(response.assistantMessages);

        final suggestedTitle = response.suggestedChatTitle;

        if (suggestedTitle != null && suggestedTitle.trim().isNotEmpty) {
          selectedChat.title = suggestedTitle.trim();
        }

        _isSendingMessage = false;
      });

      _scrollToLatestMessage();
    } catch (error, stackTrace) {
      debugPrint('Conversation send failed: $error');
      debugPrintStack(stackTrace: stackTrace);

      if (!mounted) {
        return;
      }

      setState(() {
        selectedChat.messages.removeWhere(
          (message) => message.id == loadingMessage?.id,
        );

        if (preparedTurn == null) {
          _messageController.text = messageText;
          _messageController.selection = TextSelection.collapsed(
            offset: _messageController.text.length,
          );
        } else {
          final travellerIndex = selectedChat.messages.indexWhere(
            (message) => message.id == preparedTurn!.travellerMessageId,
          );

          if (travellerIndex != -1) {
            selectedChat.messages[travellerIndex] = selectedChat
                .messages[travellerIndex]
                .copyWith(
                  deliveryStatus: ConversationMessageDeliveryStatus.failed,
                );
          }
        }

        _isSendingMessage = false;
      });

      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(
          const SnackBar(
            content: Text('Unable to send the message. Please try again.'),
            behavior: SnackBarBehavior.floating,
          ),
        );
    }
  }

  Future<void> _openStoredChat(_ChatEntry chatEntry) async {
    Navigator.of(context).pop();

    final chatId = chatEntry.id;

    final selectedIndex = _chatHistory.indexWhere(
      (entry) => identical(entry, chatEntry) || entry.id == chatId,
    );

    if (selectedIndex >= 0) {
      setState(() {
        _selectedChatIndex = selectedIndex;
      });
    }

    if (chatId == null || chatEntry.messages.isNotEmpty) {
      return;
    }

    final user = FirebaseAuth.instance.currentUser;

    if (user == null) {
      return;
    }

    try {
      final messages = await _conversationStoreService.loadMessages(
        uid: user.uid,
        chatId: chatId,
      );

      if (!mounted) {
        return;
      }

      final currentIndex = _chatHistory.indexWhere(
        (entry) => entry.id == chatId,
      );

      if (currentIndex < 0) {
        return;
      }

      setState(() {
        _chatHistory[currentIndex].messages
          ..clear()
          ..addAll(messages);

        _selectedChatIndex = currentIndex;
      });

      _scrollToLatestMessage();
    } catch (error, stackTrace) {
      debugPrint('Unable to load saved chat: $error');
      debugPrintStack(stackTrace: stackTrace);

      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Unable to load this conversation.')),
      );
    }
  }

  void _startNewChat() {
    final existingBlankIndex = _chatHistory.indexWhere(
      (entry) =>
          entry.id == null &&
          entry.messages.isEmpty &&
          !_hasMeaningfulChatTitle(entry),
    );

    setState(() {
      if (existingBlankIndex >= 0) {
        _selectedChatIndex = existingBlankIndex;
      } else {
        _chatHistory.insert(0, _ChatEntry('New chat'));
        _selectedChatIndex = 0;
      }
    });

    Navigator.of(context).pop();
  }

  Future<void> _deleteChat(int index) async {
    if (index < 0 || index >= _chatHistory.length) {
      return;
    }

    final chatEntry = _chatHistory[index];
    final chatId = chatEntry.id;

    if (chatId != null) {
      final user = FirebaseAuth.instance.currentUser;

      if (user == null) {
        if (!mounted) {
          return;
        }

        _showMessage('Unable to delete the conversation.');
        return;
      }

      try {
        await _conversationStoreService.deleteChat(
          uid: user.uid,
          chatId: chatId,
        );
      } catch (error, stackTrace) {
        debugPrint('Unable to delete saved chat: $error');
        debugPrintStack(stackTrace: stackTrace);

        if (!mounted) {
          return;
        }

        _showMessage('Unable to delete the conversation.');

        return;
      }
    }

    if (!mounted) {
      return;
    }

    final currentIndex = chatId == null
        ? _chatHistory.indexOf(chatEntry)
        : _chatHistory.indexWhere((entry) => entry.id == chatId);

    final selectedEntry = _selectedChat;
    final deletedSelectedChat = identical(selectedEntry, chatEntry);

    setState(() {
      if (currentIndex >= 0) {
        _chatHistory.removeAt(currentIndex);
      } else {
        _chatHistory.removeWhere(
          (entry) => identical(entry, chatEntry) || entry.id == chatId,
        );
      }

      if (_chatHistory.isEmpty) {
        _chatHistory.add(_ChatEntry('New chat'));
        _selectedChatIndex = 0;
        return;
      }

      if (deletedSelectedChat) {
        _selectedChatIndex = currentIndex < _chatHistory.length
            ? currentIndex
            : _chatHistory.length - 1;
        return;
      }

      final selectedChatId = selectedEntry.id;

      if (selectedChatId != null) {
        _selectedChatIndex = _chatHistory.indexWhere(
          (entry) => entry.id == selectedChatId,
        );
      } else {
        _selectedChatIndex = _chatHistory.indexOf(selectedEntry);
      }

      if (_selectedChatIndex < 0) {
        _selectedChatIndex = 0;
      }
    });

    if (!mounted) {
      return;
    }

    _showSuccessMessage('Conversation deleted.');
  }

  Future<bool> _confirmDeleteChat(int index) async {
    if (index < 0 || index >= _chatHistory.length) return false;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        final theme = Theme.of(context);
        return AlertDialog(
          title: const Text('Delete chat'),
          content: const Text('Are you sure you want to delete this chat?'),
          actions: [
            TextButton(
              style: TextButton.styleFrom(
                foregroundColor: theme.colorScheme.onSurface,
              ),
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            TextButton(
              style: TextButton.styleFrom(
                foregroundColor: theme.colorScheme.error,
              ),
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Delete'),
            ),
          ],
        );
      },
    );
    return confirmed ?? false;
  }

  Future<void> _showChatActionsPopup(Offset position, int index) async {
    if (index < 0 || index >= _chatHistory.length) return;
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final chatEntry = _chatHistory[index];

    final result = await showDialog<String>(
      context: context,
      builder: (context) {
        return Dialog(
          insetPadding: const EdgeInsets.symmetric(
            horizontal: 20,
            vertical: 24,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(24),
          ),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 360),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(24, 24, 24, 18),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          color: colorScheme.primary.withValues(alpha: 0.11),
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: Icon(
                          Icons.chat_bubble_outline_rounded,
                          color: colorScheme.primary,
                        ),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Text(
                          'Chat actions',
                          style: theme.textTheme.titleLarge?.copyWith(
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Choose what you want to do with this conversation.',
                    style: theme.textTheme.bodyMedium?.copyWith(height: 1.45),
                  ),
                  const SizedBox(height: 12),
                  ListTile(
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 4,
                      vertical: 2,
                    ),
                    leading: Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: colorScheme.surfaceContainerHighest,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Icon(
                        Icons.edit_outlined,
                        color: colorScheme.primary,
                      ),
                    ),
                    title: const Text('Rename'),
                    trailing: Icon(
                      Icons.chevron_right_rounded,
                      color: colorScheme.onSurfaceVariant,
                    ),
                    onTap: () => Navigator.of(context).pop('rename'),
                  ),
                  ListTile(
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 4,
                      vertical: 2,
                    ),
                    leading: Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: colorScheme.surfaceContainerHighest,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Icon(
                        chatEntry.pinned
                            ? Icons.push_pin_rounded
                            : Icons.push_pin_outlined,
                        color: colorScheme.primary,
                      ),
                    ),
                    title: Text(chatEntry.pinned ? 'Unpin' : 'Pin'),
                    trailing: Icon(
                      Icons.chevron_right_rounded,
                      color: colorScheme.onSurfaceVariant,
                    ),
                    onTap: () => Navigator.of(
                      context,
                    ).pop(chatEntry.pinned ? 'unpin' : 'pin'),
                  ),
                  ListTile(
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 4,
                      vertical: 2,
                    ),
                    leading: Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: colorScheme.error.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Icon(
                        Icons.delete_outline,
                        color: colorScheme.error,
                      ),
                    ),
                    title: Text(
                      'Delete',
                      style: TextStyle(color: colorScheme.error),
                    ),
                    trailing: Icon(
                      Icons.chevron_right_rounded,
                      color: colorScheme.onSurfaceVariant,
                    ),
                    onTap: () => Navigator.of(context).pop('delete'),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );

    if (result == null) return;
    switch (result) {
      case 'rename':
        _renameChat(index);
        break;
      case 'pin':
      case 'unpin':
        _pinChat(index);
        break;
      case 'delete':
        if (await _confirmDeleteChat(index)) {
          await _deleteChat(index);
        }
        break;
    }
  }

  Future<void> _pinChat(int index) async {
    if (index < 0 || index >= _chatHistory.length) {
      return;
    }

    final chatEntry = _chatHistory[index];
    final previousPinnedValue = chatEntry.pinned;
    final newPinnedValue = !previousPinnedValue;
    final selectedChatId = _selectedChat.id;
    final selectedChatEntry = _selectedChat;

    void updateLocalPinnedValue(bool pinned) {
      if (!mounted) {
        return;
      }

      setState(() {
        chatEntry.pinned = pinned;

        _chatHistory.sort((first, second) {
          if (first.pinned && !second.pinned) {
            return -1;
          }

          if (!first.pinned && second.pinned) {
            return 1;
          }

          return 0;
        });

        if (selectedChatId != null) {
          _selectedChatIndex = _chatHistory.indexWhere(
            (entry) => entry.id == selectedChatId,
          );
        } else {
          _selectedChatIndex = _chatHistory.indexOf(selectedChatEntry);
        }

        if (_selectedChatIndex < 0) {
          _selectedChatIndex = 0;
        }
      });
    }

    updateLocalPinnedValue(newPinnedValue);

    final chatId = chatEntry.id;

    if (chatId == null) {
      return;
    }

    final user = FirebaseAuth.instance.currentUser;

    if (user == null) {
      updateLocalPinnedValue(previousPinnedValue);
      return;
    }

    try {
      await _conversationStoreService.setChatPinned(
        uid: user.uid,
        chatId: chatId,
        pinned: newPinnedValue,
      );
    } catch (error, stackTrace) {
      debugPrint('Unable to update chat pin: $error');
      debugPrintStack(stackTrace: stackTrace);

      updateLocalPinnedValue(previousPinnedValue);

      if (!mounted) {
        return;
      }

      _showMessage('Unable to update the conversation pin.');
      return;
    }

    if (!mounted) {
      return;
    }

    _showSuccessMessage(
      newPinnedValue ? 'Conversation pinned.' : 'Conversation unpinned.',
    );
  }

  Future<void> _renameChat(int index) async {
    if (index < 0 || index >= _chatHistory.length) {
      return;
    }

    final chatEntry = _chatHistory[index];

    final newTitle = await showDialog<String?>(
      context: context,
      builder: (context) {
        final theme = Theme.of(context);
        final colorScheme = theme.colorScheme;
        final controller = TextEditingController(text: chatEntry.title);
        return Dialog(
          insetPadding: const EdgeInsets.symmetric(
            horizontal: 20,
            vertical: 24,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(24),
          ),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 360),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(24, 24, 24, 18),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          color: colorScheme.primary.withValues(alpha: 0.11),
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: Icon(
                          Icons.edit_outlined,
                          color: colorScheme.primary,
                        ),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Text(
                          'Rename chat',
                          style: theme.textTheme.titleLarge?.copyWith(
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Give this conversation a clearer name.',
                    style: theme.textTheme.bodyMedium?.copyWith(height: 1.45),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: controller,
                    autofocus: true,
                    decoration: InputDecoration(
                      hintText: 'Chat name',
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                      prefixIcon: const Icon(Icons.chat_bubble_outline_rounded),
                    ),
                  ),
                  const SizedBox(height: 18),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      TextButton(
                        style: TextButton.styleFrom(
                          foregroundColor: theme.colorScheme.onSurface,
                        ),
                        onPressed: () => Navigator.of(context).pop(),
                        child: const Text('Cancel'),
                      ),
                      const SizedBox(width: 8),
                      FilledButton(
                        onPressed: () =>
                            Navigator.of(context).pop(controller.text.trim()),
                        child: const Text('Save'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );

    if (newTitle == null) {
      return;
    }

    final normalizedTitle = newTitle.trim();

    if (normalizedTitle.isEmpty) {
      return;
    }

    final titleWordCount = normalizedTitle
        .split(RegExp(r'\s+'))
        .where((word) => word.isNotEmpty)
        .length;

    if (titleWordCount < 3 || titleWordCount > 5) {
      if (!mounted) {
        return;
      }

      _showWarningMessage('The chat name must contain 3 to 5 words.');

      return;
    }

    final previousTitle = chatEntry.title;

    setState(() {
      chatEntry.title = normalizedTitle;
    });

    final chatId = chatEntry.id;

    if (chatId == null) {
      return;
    }

    final user = FirebaseAuth.instance.currentUser;

    if (user == null) {
      setState(() {
        chatEntry.title = previousTitle;
      });

      return;
    }

    try {
      await _conversationStoreService.updateChatTitle(
        uid: user.uid,
        chatId: chatId,
        title: normalizedTitle,
      );

      if (!mounted) {
        return;
      }

      _showSuccessMessage('Conversation renamed.');
    } catch (error, stackTrace) {
      debugPrint('Unable to rename saved chat: $error');
      debugPrintStack(stackTrace: stackTrace);

      if (!mounted) {
        return;
      }

      setState(() {
        chatEntry.title = previousTitle;
      });

      _showMessage('Unable to rename the conversation.');
    }
  }

  void _showSnackBar(
    String message,
    Color backgroundColor,
    Icon icon, [
    Duration duration = const Duration(seconds: 4),
  ]) {
    _drawerFeedbackTimer?.cancel();

    if (!mounted) {
      return;
    }

    setState(() {
      _drawerFeedbackMessage = message;
      _drawerFeedbackColor = backgroundColor;
      _drawerFeedbackIcon = icon.icon;
    });

    _drawerFeedbackTimer = Timer(duration, () {
      if (!mounted) {
        return;
      }

      setState(() {
        _drawerFeedbackMessage = null;
      });
    });
  }

  void _showMessage(String message) {
    _showSnackBar(
      message,
      AppColors.error,
      const Icon(Icons.error_outline_rounded, color: AppColors.white),
    );
  }

  void _showSuccessMessage(
    String message, [
    Duration duration = const Duration(seconds: 3),
  ]) {
    _showSnackBar(
      message,
      AppColors.success,
      const Icon(Icons.check_circle_outline_rounded, color: AppColors.white),
      duration,
    );
  }

  void _showWarningMessage(
    String message, [
    Duration duration = const Duration(seconds: 4),
  ]) {
    _showSnackBar(
      message,
      AppColors.warning,
      const Icon(Icons.warning_amber_rounded, color: AppColors.white),
      duration,
    );
  }

  String get _profileInitials {
    final user = FirebaseAuth.instance.currentUser;
    final name = user?.displayName?.trim();
    if (name != null && name.isNotEmpty) {
      final parts = name.split(RegExp(r'\s+')).where((part) => part.isNotEmpty);
      if (parts.length >= 2) {
        return '${parts.first[0]}${parts.last[0]}'.toUpperCase();
      }
      return parts.first.substring(0, 1).toUpperCase();
    }

    final email = user?.email?.trim() ?? '';
    if (email.isNotEmpty) {
      return email[0].toUpperCase();
    }

    return 'U';
  }

  Widget _buildTopButton({
    required Widget icon,
    required VoidCallback onTap,
    required Color backgroundColor,
    required Color borderColor,
  }) {
    return Container(
      height: 48,
      width: 48,
      decoration: BoxDecoration(
        color: backgroundColor,
        shape: BoxShape.circle,
        border: Border.all(color: borderColor, width: 1),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: onTap,
        child: Center(child: icon),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final iconColor = theme.brightness == Brightness.dark
        ? AppColors.white
        : colorScheme.onSurface;
    final statusBarTop = MediaQuery.paddingOf(context).top;
    final messagesTopPadding = statusBarTop + 76.0;
    final buttonBackgroundColor = colorScheme.surfaceContainerHighest
        .withValues(alpha: 0.42);
    final pillBorderColor = colorScheme.surfaceContainerHighest.withValues(
      alpha: 0.2,
    );
    final drawerDividerColor = colorScheme.onSurface.withValues(alpha: 0.18);

    final visibleDrawerChats = _chatHistory
        .where(_hasMeaningfulChatTitle)
        .toList();

    final pinnedDrawerChats = visibleDrawerChats
        .where((entry) => entry.pinned)
        .toList();

    final recentDrawerChats = visibleDrawerChats
        .where((entry) => !entry.pinned)
        .toList();

    Widget buildDrawerChatTile(_ChatEntry chatEntry) {
      final actualIndex = _chatHistory.indexOf(chatEntry);
      final selected = actualIndex == _selectedChatIndex;

      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
        child: Material(
          color: selected
              ? colorScheme.surfaceContainerHighest.withValues(alpha: 0.42)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(16),
          clipBehavior: Clip.antiAlias,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onLongPressStart: (details) {
              _showChatActionsPopup(details.globalPosition, actualIndex);
            },
            child: ListTile(
              title: Text(
                chatEntry.title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              onTap: () {
                _openStoredChat(chatEntry);
              },
              contentPadding: const EdgeInsets.symmetric(
                horizontal: 16,
                vertical: 2,
              ),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
            ),
          ),
        ),
      );
    }

    return Scaffold(
      backgroundColor: colorScheme.surface,
      key: _scaffoldKey,
      drawer: Drawer(
        shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
        backgroundColor: colorScheme.surface,
        child: DecoratedBox(
          decoration: BoxDecoration(
            border: Border(
              right: BorderSide(color: drawerDividerColor, width: 1),
            ),
          ),
          child: SafeArea(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 20,
                    vertical: 20,
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          'Trip Logic',
                          style: theme.textTheme.headlineSmall?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                      Container(
                        height: 48,
                        width: 48,
                        decoration: BoxDecoration(
                          color: buttonBackgroundColor,
                          shape: BoxShape.circle,
                          border: Border.all(color: pillBorderColor, width: 1),
                        ),
                        child: InkWell(
                          borderRadius: BorderRadius.circular(999),
                          onTap: _openSearch,
                          child: Center(
                            child: Icon(
                              Icons.search,
                              size: 22,
                              color: iconColor,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: ListView(
                    padding: const EdgeInsets.only(bottom: 8),
                    children: [
                      if (pinnedDrawerChats.isNotEmpty) ...[
                        Padding(
                          padding: const EdgeInsets.fromLTRB(20, 12, 20, 6),
                          child: Text(
                            'Pinned',
                            style: theme.textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.w700,
                              color: colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ),
                        ...pinnedDrawerChats.map(buildDrawerChatTile),
                        const SizedBox(height: 8),
                      ],
                      Padding(
                        padding: const EdgeInsets.fromLTRB(20, 10, 20, 6),
                        child: Text(
                          'Recents',
                          style: theme.textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w700,
                            color: colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ),
                      if (recentDrawerChats.isEmpty)
                        Padding(
                          padding: const EdgeInsets.fromLTRB(20, 4, 20, 14),
                          child: Text(
                            'No recent chats yet',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: colorScheme.onSurfaceVariant,
                            ),
                          ),
                        )
                      else
                        ...recentDrawerChats.map(buildDrawerChatTile),
                    ],
                  ),
                ),
                if (_drawerFeedbackMessage != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 12,
                      ),
                      decoration: BoxDecoration(
                        color: _drawerFeedbackColor,
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            _drawerFeedbackIcon,
                            color: AppColors.white,
                            size: 20,
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              _drawerFeedbackMessage!,
                              style: const TextStyle(
                                color: AppColors.white,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
                  child: Row(
                    children: [
                      Expanded(
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: ElevatedButton.icon(
                            style: ElevatedButton.styleFrom(
                              backgroundColor: colorScheme.primary,
                              foregroundColor: colorScheme.onPrimary,
                              padding: const EdgeInsets.symmetric(
                                vertical: 14,
                                horizontal: 20,
                              ),
                              shape: const StadiumBorder(),
                            ),
                            onPressed: _startNewChat,
                            icon: const Icon(Icons.edit_outlined, size: 20),
                            label: const Text('Chat'),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Container(
                        height: 48,
                        width: 48,
                        decoration: BoxDecoration(
                          color: buttonBackgroundColor,
                          shape: BoxShape.circle,
                          border: Border.all(color: pillBorderColor, width: 1),
                        ),
                        child: InkWell(
                          borderRadius: BorderRadius.circular(999),
                          onTap: _openProfile,
                          child: Center(
                            child: Container(
                              height: 34,
                              width: 34,
                              decoration: const BoxDecoration(
                                color: Color(0xFF1F7A5A),
                                shape: BoxShape.circle,
                              ),
                              alignment: Alignment.center,
                              child: Text(
                                _profileInitials,
                                style: theme.textTheme.bodyMedium?.copyWith(
                                  fontWeight: FontWeight.w700,
                                  color: Colors.white,
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
      body: Stack(
        fit: StackFit.expand,
        children: [
          SafeArea(
            top: false,
            child: Column(
              children: [
                Expanded(
                  child: ListView(
                    controller: _scrollController,
                    padding: EdgeInsets.fromLTRB(16, messagesTopPadding, 16, 8),
                    children: [
                      for (final message in _selectedMessages)
                        Align(
                          alignment: message.isFromTraveller
                              ? Alignment.centerRight
                              : Alignment.centerLeft,
                          child: Container(
                            constraints: BoxConstraints(
                              maxWidth:
                                  MediaQuery.of(context).size.width *
                                  (message.hasRecommendationGroups
                                      ? 0.94
                                      : 0.78),
                            ),
                            margin: const EdgeInsets.only(bottom: 10),
                            padding: const EdgeInsets.symmetric(
                              horizontal: 16,
                              vertical: 12,
                            ),
                            decoration: BoxDecoration(
                              color: message.isFromTraveller
                                  ? colorScheme.primary
                                  : colorScheme.surfaceContainerHighest,
                              borderRadius: BorderRadius.circular(18),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                if (message.type ==
                                    ConversationMessageType.loading)
                                  Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      SizedBox(
                                        width: 14,
                                        height: 14,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                          color: colorScheme.primary,
                                        ),
                                      ),
                                      const SizedBox(width: 10),
                                      Text(
                                        'Thinking...',
                                        style: theme.textTheme.bodyMedium
                                            ?.copyWith(
                                              color:
                                                  colorScheme.onSurfaceVariant,
                                              fontStyle: FontStyle.italic,
                                            ),
                                      ),
                                    ],
                                  )
                                else if (shouldRenderConversationMessageText(
                                  message,
                                ))
                                  Text(
                                    message.text,
                                    style: theme.textTheme.bodyMedium?.copyWith(
                                      color: message.isFromTraveller
                                          ? colorScheme.onPrimary
                                          : colorScheme.onSurface,
                                    ),
                                  ),
                                if (message.hasRecommendationGroups)
                                  for (final group
                                      in message.recommendationGroups)
                                    RecommendationGroupView(group: group),
                                if (message.hasFailed) ...[
                                  const SizedBox(height: 6),
                                  Text(
                                    'Not delivered',
                                    style: theme.textTheme.labelSmall?.copyWith(
                                      color: message.isFromTraveller
                                          ? colorScheme.onPrimary
                                          : colorScheme.error,
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.all(16),
                  color: colorScheme.surface,
                  child: Row(
                    children: [
                      Expanded(
                        child: Container(
                          height: 60,
                          padding: const EdgeInsets.only(left: 12, right: 10),
                          decoration: BoxDecoration(
                            color: colorScheme.surfaceContainerHighest
                                .withValues(alpha: 0.42),
                            borderRadius: BorderRadius.circular(28),
                            border: Border.all(
                              color: pillBorderColor,
                              width: 1,
                            ),
                          ),
                          child: Row(
                            children: [
                              Expanded(
                                child: TextField(
                                  controller: _messageController,
                                  style: theme.textTheme.bodyMedium,
                                  cursorColor: colorScheme.onSurface,
                                  textInputAction: TextInputAction.send,
                                  onChanged: (_) => setState(() {}),
                                  onSubmitted: (_) => _handleSendPressed(),
                                  decoration: InputDecoration(
                                    hintText: 'Type a message...',
                                    hintStyle: theme.textTheme.bodyMedium,
                                    border: InputBorder.none,
                                    isDense: true,
                                    contentPadding: const EdgeInsets.symmetric(
                                      horizontal: 10,
                                    ),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 6),
                              Container(
                                height: 44,
                                width: 44,
                                decoration: BoxDecoration(
                                  color: _canSendMessage
                                      ? colorScheme.primary
                                      : colorScheme.surfaceContainerHighest,
                                  borderRadius: BorderRadius.circular(22),
                                ),
                                child: IconButton(
                                  icon: const Icon(
                                    Icons.send_rounded,
                                    size: 20,
                                  ),
                                  color: _canSendMessage
                                      ? colorScheme.onPrimary
                                      : colorScheme.onSurface.withValues(
                                          alpha: 0.5,
                                        ),
                                  onPressed: _canSendMessage
                                      ? _handleSendPressed
                                      : null,
                                  padding: EdgeInsets.zero,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Positioned(
            top: statusBarTop + 15,
            left: 20,
            child: _buildTopButton(
              icon: Icon(Icons.menu_rounded, size: 24, color: iconColor),
              onTap: _openMenu,
              backgroundColor: buttonBackgroundColor,
              borderColor: pillBorderColor,
            ),
          ),
        ],
      ),
    );
  }
}

class ChatSearchPage extends StatefulWidget {
  const ChatSearchPage({
    super.key,
    required this.chatHistory,
    required this.selectedChat,
  });

  final List<String> chatHistory;
  final String selectedChat;

  @override
  State<ChatSearchPage> createState() => _ChatSearchPageState();
}

class _ChatSearchPageState extends State<ChatSearchPage> {
  late final TextEditingController _searchController;
  String _query = '';

  @override
  void initState() {
    super.initState();
    _searchController = TextEditingController();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  List<String> get _filteredChats {
    if (_query.isEmpty) {
      return widget.chatHistory;
    }

    return widget.chatHistory
        .where((chat) => chat.toLowerCase().contains(_query.toLowerCase()))
        .toList();
  }

  void _updateQuery(String query) {
    setState(() {
      _query = query;
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Search chats')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Container(
              height: 60,
              padding: const EdgeInsets.only(left: 12, right: 10),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest.withValues(
                  alpha: 0.42,
                ),
                borderRadius: BorderRadius.circular(28),
                border: Border.all(
                  color: theme.colorScheme.surfaceContainerHighest.withValues(
                    alpha: 0.2,
                  ),
                  width: 1,
                ),
              ),
              child: Row(
                children: [
                  const Icon(Icons.search),
                  const SizedBox(width: 10),
                  Expanded(
                    child: TextField(
                      controller: _searchController,
                      onChanged: _updateQuery,
                      autofocus: true,
                      style: theme.textTheme.bodyMedium,
                      cursorColor: theme.colorScheme.onSurface,
                      decoration: InputDecoration(
                        hintText: 'Search chats',
                        hintStyle: theme.textTheme.bodyMedium,
                        border: InputBorder.none,
                        isDense: true,
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: 10,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          Expanded(
            child: _filteredChats.isEmpty
                ? Center(
                    child: Text(
                      'No chats found',
                      style: theme.textTheme.bodyLarge,
                    ),
                  )
                : ListView.builder(
                    itemCount: _filteredChats.length,
                    itemBuilder: (context, index) {
                      final chat = _filteredChats[index];
                      final selected = chat == widget.selectedChat;
                      return ListTile(
                        title: Text(chat),
                        trailing: selected ? const Icon(Icons.check) : null,
                        onTap: () => Navigator.of(context).pop(chat),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
