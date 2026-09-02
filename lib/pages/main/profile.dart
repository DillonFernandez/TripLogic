import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:phone_form_field/phone_form_field.dart';
import 'package:trip_logic/theme/app_colors.dart';
import 'package:trip_logic/theme/app_theme.dart';

const _profileDialogShape = RoundedRectangleBorder(
  borderRadius: BorderRadius.all(Radius.circular(24)),
);

const _profileDialogInputBorder = OutlineInputBorder(
  borderRadius: BorderRadius.all(Radius.circular(16)),
  borderSide: BorderSide.none,
);

class ProfilePage extends StatefulWidget {
  const ProfilePage({super.key});

  @override
  State<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> with WidgetsBindingObserver {
  static final _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');
  static final _whitespacePattern = RegExp(r'\s+');

  final GlobalKey<FormState> _profileFormKey = GlobalKey<FormState>();
  final ScrollController _scrollController = ScrollController();

  bool _isSendingReset = false;
  bool _isSigningOut = false;
  late final PhoneController _phoneController;

  DateTime? _dateOfBirth;

  String _fullName = '';
  String _profileEmail = '';

  Timer? _emailChangeCheckTimer;
  Timer? _emailChangeExpiryTimer;

  String? _pendingNewEmail;
  String? _pendingEmailPassword;

  bool _isCheckingEmailChange = false;
  bool _isLoadingProfile = true;
  bool _isSavingProfile = false;
  ThemeMode _selectedThemeMode = ThemeMode.system;

  static IsoCode _deviceIsoCode() {
    final countryCode = WidgetsBinding
        .instance
        .platformDispatcher
        .locale
        .countryCode
        ?.toUpperCase();

    if (countryCode == null || countryCode.isEmpty) {
      return IsoCode.US;
    }

    return IsoCode.values.firstWhere(
      (isoCode) => isoCode.name == countryCode,
      orElse: () => IsoCode.US,
    );
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);

    _phoneController = PhoneController(
      initialValue: PhoneNumber(isoCode: _deviceIsoCode(), nsn: ''),
    );

    _selectedThemeMode = appThemeModeNotifier.value;
    appThemeModeNotifier.addListener(_handleThemeModeChanged);

    unawaited(_loadProfileDetails());
  }

  void _startEmailChangeWatcher({
    required String newEmail,
    required String currentPassword,
  }) {
    _emailChangeCheckTimer?.cancel();
    _emailChangeExpiryTimer?.cancel();

    _pendingNewEmail = newEmail.trim().toLowerCase();
    _pendingEmailPassword = currentPassword;

    unawaited(_checkPendingEmailChange());

    _emailChangeCheckTimer = Timer.periodic(
      const Duration(seconds: 5),
      (_) => unawaited(_checkPendingEmailChange()),
    );

    _emailChangeExpiryTimer = Timer(
      const Duration(minutes: 15),
      _stopEmailChangeWatcher,
    );
  }

  void _stopEmailChangeWatcher() {
    _emailChangeCheckTimer?.cancel();
    _emailChangeExpiryTimer?.cancel();

    _emailChangeCheckTimer = null;
    _emailChangeExpiryTimer = null;

    _pendingNewEmail = null;
    _pendingEmailPassword = null;
  }

  static bool _isExpiredSessionError(String code) =>
      code == 'user-token-expired' ||
      code == 'invalid-user-token' ||
      code == 'user-not-found';

  Future<void> _checkPendingEmailChange() async {
    if (_isCheckingEmailChange) return;

    final newEmail = _pendingNewEmail;
    final password = _pendingEmailPassword;

    if (newEmail == null || password == null) return;

    _isCheckingEmailChange = true;

    try {
      User? user = FirebaseAuth.instance.currentUser;

      if (user != null) {
        try {
          await user.reload();
          user = FirebaseAuth.instance.currentUser;

          final refreshedEmail = user?.email?.trim().toLowerCase();

          if (refreshedEmail != newEmail) {
            return;
          }
        } on FirebaseAuthException catch (error) {
          if (!_isExpiredSessionError(error.code)) {
            rethrow;
          }
        }
      }

      final credential = await FirebaseAuth.instance.signInWithEmailAndPassword(
        email: newEmail,
        password: password,
      );

      user = credential.user;

      if (user == null) return;

      final signedInEmail = user.email?.trim().toLowerCase();

      if (signedInEmail != newEmail) return;

      await user.getIdToken(true);

      await FirebaseFirestore.instance.collection('users').doc(user.uid).update(
        {'email': newEmail, 'updatedAt': FieldValue.serverTimestamp()},
      );

      _stopEmailChangeWatcher();

      if (!mounted) return;

      setState(() {
        _profileEmail = newEmail;
      });

      _showMessage('Your email has been verified and updated successfully.');
    } on FirebaseAuthException catch (error) {
      if (error.code == 'invalid-credential' ||
          error.code == 'wrong-password' ||
          error.code == 'user-not-found') {
        return;
      }

      if (error.code == 'network-request-failed') {
        return;
      }

      if (error.code == 'too-many-requests') {
        _stopEmailChangeWatcher();

        if (mounted) {
          _showMessage(
            'Too many verification checks. Please wait and try again.',
            isError: true,
          );
        }

        return;
      }

      _stopEmailChangeWatcher();

      if (mounted) {
        _showMessage(
          error.message ?? 'Unable to finish changing your email.',
          isError: true,
        );
      }
    } on FirebaseException catch (error) {
      if (error.code == 'unavailable') return;

      _stopEmailChangeWatcher();

      if (mounted) {
        _showMessage(
          error.message ?? 'Unable to update your Firestore profile.',
          isError: true,
        );
      }
    } finally {
      _isCheckingEmailChange = false;
    }
  }

  Future<void> _syncVerifiedEmail() async {
    final existingUser = FirebaseAuth.instance.currentUser;

    if (existingUser == null) return;

    try {
      await existingUser.reload();

      final refreshedUser = FirebaseAuth.instance.currentUser;
      final refreshedEmail = refreshedUser?.email?.trim();

      if (refreshedUser == null ||
          refreshedEmail == null ||
          refreshedEmail.isEmpty) {
        return;
      }

      await refreshedUser.getIdToken(true);

      final userDocument = FirebaseFirestore.instance
          .collection('users')
          .doc(refreshedUser.uid);

      final snapshot = await userDocument.get();
      final storedEmail = snapshot.data()?['email'];
      final firestoreEmail = storedEmail is String ? storedEmail.trim() : '';

      if (firestoreEmail != refreshedEmail) {
        await userDocument.update({
          'email': refreshedEmail,
          'updatedAt': FieldValue.serverTimestamp(),
        });

        if (!mounted) return;

        setState(() {
          _profileEmail = refreshedEmail;
        });

        _showMessage('Your new email address has been verified and updated.');
        return;
      }

      if (!mounted || _profileEmail == refreshedEmail) return;

      setState(() {
        _profileEmail = refreshedEmail;
      });
    } on FirebaseException {
      // Ignore profile sync failures; the UI can still load existing data.
    }
  }

  Future<void> _loadProfileDetails() async {
    final user = FirebaseAuth.instance.currentUser;

    if (user == null) {
      if (!mounted) return;

      setState(() {
        _isLoadingProfile = false;
      });

      return;
    }

    try {
      await _syncVerifiedEmail();

      final snapshot = await FirebaseFirestore.instance
          .collection('users')
          .doc(user.uid)
          .get();

      final data = snapshot.data();
      final storedFullName = data?['fullName'];
      final storedEmail = data?['email'];
      final storedPhoneNumber = data?['phoneNumber'];
      final storedDateOfBirth = data?['dateOfBirth'];

      PhoneNumber? parsedPhoneNumber;

      if (storedPhoneNumber is String && storedPhoneNumber.trim().isNotEmpty) {
        try {
          parsedPhoneNumber = PhoneNumber.parse(storedPhoneNumber.trim());
        } catch (_) {
          parsedPhoneNumber = null;
        }
      }

      DateTime? parsedDateOfBirth;

      if (storedDateOfBirth is Timestamp) {
        final storedDate = storedDateOfBirth.toDate().toUtc();

        parsedDateOfBirth = DateTime(
          storedDate.year,
          storedDate.month,
          storedDate.day,
        );
      }

      if (!mounted) return;

      if (parsedPhoneNumber != null) {
        _phoneController.value = parsedPhoneNumber;
      }

      setState(() {
        _fullName = storedFullName is String
            ? storedFullName.trim()
            : (user.displayName?.trim() ?? '');

        _profileEmail = storedEmail is String
            ? storedEmail.trim()
            : (user.email?.trim() ?? '');

        _dateOfBirth = parsedDateOfBirth;
        _isLoadingProfile = false;
      });
    } catch (error) {
      if (!mounted) return;

      setState(() {
        _isLoadingProfile = false;
      });

      _showMessage(
        error is FirebaseException
            ? error.message ?? 'Unable to load your profile information.'
            : 'Unable to load your profile information.',
        isError: true,
      );
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _phoneController.dispose();
    _scrollController.dispose();
    appThemeModeNotifier.removeListener(_handleThemeModeChanged);
    _stopEmailChangeWatcher();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_checkPendingEmailChange());
      unawaited(_syncVerifiedEmail());
    }
  }

  void _handleThemeModeChanged() {
    final mode = appThemeModeNotifier.value;
    if (!mounted || mode == _selectedThemeMode) return;

    setState(() {
      _selectedThemeMode = mode;
    });
  }

  String get _profileInitials {
    final name = _fullName.trim();
    if (name.isNotEmpty) {
      final parts = name.split(_whitespacePattern);
      if (parts.length >= 2) {
        return '${parts.first[0]}${parts.last[0]}'.toUpperCase();
      }
      return parts.first.substring(0, 1).toUpperCase();
    }

    final email = _profileEmail.trim();
    if (email.isNotEmpty) {
      return email[0].toUpperCase();
    }

    return 'U';
  }

  int get _profileCompletionPercent =>
      25 *
      ((_fullName.trim().isNotEmpty ? 1 : 0) +
          (_profileEmail.trim().isNotEmpty ? 1 : 0) +
          (_phoneController.value.nsn.trim().isNotEmpty ? 1 : 0) +
          (_dateOfBirth == null ? 0 : 1));

  Future<void> _setThemeMode(ThemeMode mode) async {
    if (mode == _selectedThemeMode) return;

    setState(() {
      _selectedThemeMode = mode;
    });

    appThemeModeNotifier.value = mode;
    await saveThemeModePreference(mode);
  }

  Future<void> _pickDateOfBirth() async {
    if (_isSavingProfile) return;

    final now = DateTime.now();
    final defaultDate = DateTime(now.year - 18, now.month, now.day);

    final selectedDate = await showDatePicker(
      context: context,
      initialDate: _dateOfBirth ?? defaultDate,
      firstDate: DateTime(1900),
      lastDate: DateTime(now.year, now.month, now.day),
      initialDatePickerMode: DatePickerMode.year,
      helpText: 'Select date of birth',
      cancelText: 'Cancel',
      confirmText: 'Select',
      builder: (pickerContext, child) {
        final pickerTheme = Theme.of(pickerContext);
        final pickerColorScheme = pickerTheme.colorScheme;

        return Theme(
          data: pickerTheme.copyWith(
            datePickerTheme: pickerTheme.datePickerTheme.copyWith(
              backgroundColor: pickerColorScheme.surface,
              surfaceTintColor: AppColors.transparent,
              headerBackgroundColor: pickerColorScheme.surfaceContainerLow,
              headerForegroundColor: pickerColorScheme.onSurface,
              shape: _profileDialogShape,
            ),
          ),
          child: child!,
        );
      },
    );

    if (selectedDate == null || !mounted) return;

    setState(() {
      _dateOfBirth = DateTime(
        selectedDate.year,
        selectedDate.month,
        selectedDate.day,
      );
    });
  }

  String _formattedDateOfBirth(BuildContext context) {
    final dateOfBirth = _dateOfBirth;

    if (dateOfBirth == null) {
      return 'Select your date of birth';
    }

    return MaterialLocalizations.of(context).formatMediumDate(dateOfBirth);
  }

  String? _validatePhoneNumber(PhoneNumber? phoneNumber) {
    final number = phoneNumber ?? _phoneController.value;

    if (number.nsn.trim().isEmpty) return null;

    return number.isValid() ? null : 'Enter a valid phone number.';
  }

  void _goBack() => Navigator.pop(context);

  Future<void> _saveProfileDetails() async {
    if (_isSavingProfile) return;

    FocusScope.of(context, createDependency: false).unfocus();

    if (!(_profileFormKey.currentState?.validate() ?? false)) return;

    final user = FirebaseAuth.instance.currentUser;

    if (user == null) {
      _showMessage(
        'You must be logged in to update your profile.',
        isError: true,
      );
      return;
    }

    final phoneNumber = _phoneController.value;
    final internationalPhoneNumber = phoneNumber.nsn.trim().isEmpty
        ? ''
        : phoneNumber.international;

    setState(() {
      _isSavingProfile = true;
    });

    try {
      final updates = <String, dynamic>{
        'phoneNumber': internationalPhoneNumber,
        'updatedAt': FieldValue.serverTimestamp(),
      };

      final dateOfBirth = _dateOfBirth;

      if (dateOfBirth == null) {
        updates['dateOfBirth'] = FieldValue.delete();
      } else {
        updates['dateOfBirth'] = Timestamp.fromDate(
          DateTime.utc(dateOfBirth.year, dateOfBirth.month, dateOfBirth.day),
        );
      }

      await FirebaseFirestore.instance
          .collection('users')
          .doc(user.uid)
          .update(updates);

      if (!mounted) return;

      setState(() {
        _isSavingProfile = false;
      });

      _showMessage('Your profile was saved successfully.');
    } catch (error) {
      if (!mounted) return;

      setState(() {
        _isSavingProfile = false;
      });

      _showMessage(
        error is FirebaseException
            ? error.message ?? 'Unable to save your profile.'
            : 'Something went wrong while saving your profile.',
        isError: true,
      );
    }
  }

  Future<void> _showChangeEmailDialog() async {
    if (_isSavingProfile) return;

    final user = FirebaseAuth.instance.currentUser;
    final currentEmail = user?.email?.trim();

    if (user == null || currentEmail == null || currentEmail.isEmpty) {
      _showMessage(
        'No email address is connected to this account.',
        isError: true,
      );
      return;
    }

    final formKey = GlobalKey<FormState>();

    String newEmail = '';
    String currentPassword = '';
    String? requestError;

    bool isSubmitting = false;
    bool showPassword = false;

    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        return StatefulBuilder(
          builder: (dialogContext, setDialogState) {
            Future<void> submitEmailChange() async {
              if (isSubmitting) return;

              if (!(formKey.currentState?.validate() ?? false)) return;

              final normalizedNewEmail = newEmail.trim().toLowerCase();

              if (normalizedNewEmail == currentEmail.toLowerCase()) {
                setDialogState(() {
                  requestError =
                      'Enter an email different from your current email.';
                });
                return;
              }

              setDialogState(() {
                isSubmitting = true;
                requestError = null;
              });

              try {
                final credential = EmailAuthProvider.credential(
                  email: currentEmail,
                  password: currentPassword,
                );

                await user.reauthenticateWithCredential(credential);
                await user.verifyBeforeUpdateEmail(normalizedNewEmail);

                _startEmailChangeWatcher(
                  newEmail: normalizedNewEmail,
                  currentPassword: currentPassword,
                );

                if (!dialogContext.mounted) return;

                Navigator.pop(dialogContext);

                if (!mounted) return;

                _showMessage(
                  'Verification sent to $normalizedNewEmail. Open the link to complete the email change.',
                );
              } on FirebaseAuthException catch (error) {
                if (!dialogContext.mounted) return;

                setDialogState(() {
                  isSubmitting = false;
                  requestError = _changeEmailErrorMessage(error);
                });
              } catch (_) {
                if (!dialogContext.mounted) return;

                setDialogState(() {
                  isSubmitting = false;
                  requestError = 'Something went wrong. Please try again.';
                });
              }
            }

            final theme = Theme.of(dialogContext);
            final colorScheme = theme.colorScheme;
            final focusedInputBorder = OutlineInputBorder(
              borderRadius: _profileDialogInputBorder.borderRadius,
              borderSide: BorderSide(color: colorScheme.primary, width: 1.5),
            );

            return AlertDialog(
              scrollable: true,
              shape: _profileDialogShape,
              titlePadding: const EdgeInsets.fromLTRB(24, 24, 24, 0),
              contentPadding: const EdgeInsets.fromLTRB(24, 18, 24, 8),
              actionsPadding: const EdgeInsets.fromLTRB(18, 8, 18, 18),
              title: const _ProfileDialogTitle(
                icon: Icons.alternate_email_rounded,
                title: 'Change email',
              ),
              content: Form(
                key: formKey,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Enter your new email and current password. The email changes only after you verify the new address.',
                      style: theme.textTheme.bodyMedium?.copyWith(height: 1.45),
                    ),
                    const SizedBox(height: 20),
                    TextFormField(
                      initialValue: currentEmail,
                      enabled: false,
                      decoration: InputDecoration(
                        labelText: 'Current email',
                        prefixIcon: const Icon(Icons.mail_outline_rounded),
                        filled: true,
                        fillColor: colorScheme.surfaceContainerLow,
                        border: _profileDialogInputBorder,
                        disabledBorder: _profileDialogInputBorder,
                      ),
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      enabled: !isSubmitting,
                      autofocus: true,
                      keyboardType: TextInputType.emailAddress,
                      textInputAction: TextInputAction.next,
                      autocorrect: false,
                      enableSuggestions: false,
                      autofillHints: const [AutofillHints.email],
                      onChanged: (value) {
                        newEmail = value;
                      },
                      validator: (value) {
                        final email = value?.trim() ?? '';

                        if (email.isEmpty) {
                          return 'Enter your new email address.';
                        }

                        if (!_emailPattern.hasMatch(email)) {
                          return 'Enter a valid email address.';
                        }

                        return null;
                      },
                      decoration: InputDecoration(
                        labelText: 'New email',
                        hintText: 'new@example.com',
                        prefixIcon: const Icon(
                          Icons.mark_email_unread_outlined,
                        ),
                        filled: true,
                        fillColor: colorScheme.surfaceContainerLow,
                        border: _profileDialogInputBorder,
                        focusedBorder: focusedInputBorder,
                      ),
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      enabled: !isSubmitting,
                      obscureText: !showPassword,
                      textInputAction: TextInputAction.done,
                      autofillHints: const [AutofillHints.password],
                      onChanged: (value) {
                        currentPassword = value;
                      },
                      onFieldSubmitted: (_) {
                        submitEmailChange();
                      },
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return 'Enter your current password.';
                        }

                        return null;
                      },
                      decoration: InputDecoration(
                        labelText: 'Current password',
                        prefixIcon: const Icon(Icons.lock_outline_rounded),
                        suffixIcon: IconButton(
                          tooltip: showPassword
                              ? 'Hide password'
                              : 'Show password',
                          onPressed: isSubmitting
                              ? null
                              : () {
                                  setDialogState(() {
                                    showPassword = !showPassword;
                                  });
                                },
                          icon: Icon(
                            showPassword
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                        ),
                        filled: true,
                        fillColor: colorScheme.surfaceContainerLow,
                        border: _profileDialogInputBorder,
                        focusedBorder: focusedInputBorder,
                      ),
                    ),
                    if (requestError != null) ...[
                      const SizedBox(height: 12),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(
                            Icons.error_outline_rounded,
                            size: 19,
                            color: colorScheme.error,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              requestError!,
                              style: theme.textTheme.bodySmall?.copyWith(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: isSubmitting
                      ? null
                      : () => Navigator.pop(dialogContext),
                  child: const Text('Cancel'),
                ),
                FilledButton(
                  onPressed: isSubmitting ? null : submitEmailChange,
                  child: isSubmitting
                      ? SizedBox.square(
                          dimension: 19,
                          child: CircularProgressIndicator(
                            strokeWidth: 2.3,
                            color: colorScheme.onPrimary,
                          ),
                        )
                      : const Text('Send verification'),
                ),
              ],
            );
          },
        );
      },
    );
  }

  static String _changeEmailErrorMessage(FirebaseAuthException error) =>
      switch (error.code) {
        'invalid-email' => 'Enter a valid new email address.',
        'email-already-in-use' =>
          'This email is already connected to another account.',
        'wrong-password' ||
        'invalid-credential' => 'Your current password is incorrect.',
        'requires-recent-login' => 'Please log out, log in again, and retry.',
        'too-many-requests' =>
          'Too many attempts. Please wait and try again later.',
        'network-request-failed' =>
          'Check your internet connection and try again.',
        'operation-not-allowed' => 'Email changes are not currently available.',
        _ => error.message ?? 'Unable to change your email.',
      };

  Future<void> _showPasswordResetDialog() async {
    final email = FirebaseAuth.instance.currentUser?.email;

    if (email == null || email.isEmpty) {
      _showMessage(
        'No email address is connected to this account.',
        isError: true,
      );
      return;
    }

    final shouldSend = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        final theme = Theme.of(dialogContext);
        final colorScheme = theme.colorScheme;

        return AlertDialog(
          scrollable: true,
          shape: _profileDialogShape,
          titlePadding: const EdgeInsets.fromLTRB(24, 24, 24, 0),
          contentPadding: const EdgeInsets.fromLTRB(24, 18, 24, 8),
          actionsPadding: const EdgeInsets.fromLTRB(18, 8, 18, 18),
          title: const _ProfileDialogTitle(
            icon: Icons.lock_reset_rounded,
            title: 'Reset password',
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'A password reset link will be sent to:',
                style: theme.textTheme.bodyMedium?.copyWith(height: 1.45),
              ),
              const SizedBox(height: 20),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 13,
                ),
                decoration: BoxDecoration(
                  color: colorScheme.surfaceContainerLow,
                  borderRadius: const BorderRadius.all(Radius.circular(16)),
                ),
                child: Row(
                  children: [
                    Icon(
                      Icons.mail_outline_rounded,
                      size: 20,
                      color: colorScheme.primary,
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        email,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              Text(
                'Check your inbox and spam folder after sending.',
                style: theme.textTheme.bodySmall,
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Send reset link'),
            ),
          ],
        );
      },
    );

    if (shouldSend != true || !mounted) return;

    await _sendPasswordResetEmail(email);
  }

  Future<void> _sendPasswordResetEmail(String email) async {
    if (_isSendingReset) return;

    setState(() => _isSendingReset = true);

    try {
      await FirebaseAuth.instance.sendPasswordResetEmail(email: email);

      if (!mounted) return;

      setState(() => _isSendingReset = false);

      _showMessage(
        'Password reset email sent to $email. Check your inbox and spam folder.',
      );
    } catch (error) {
      if (!mounted) return;

      setState(() => _isSendingReset = false);

      _showMessage(
        error is FirebaseAuthException
            ? _passwordResetErrorMessage(error)
            : 'Something went wrong. Please try again.',
        isError: true,
      );
    }
  }

  static String _passwordResetErrorMessage(FirebaseAuthException error) =>
      switch (error.code) {
        'invalid-email' => 'The account email address is invalid.',
        'user-not-found' => 'No account was found for this email address.',
        'too-many-requests' =>
          'Too many requests. Please wait and try again later.',
        'network-request-failed' =>
          'Check your internet connection and try again.',
        'operation-not-allowed' => 'Password reset is not currently available.',
        _ => error.message ?? 'Unable to send the password reset email.',
      };

  Future<void> _showLogoutDialog() async {
    final shouldLogout = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        final theme = Theme.of(dialogContext);

        return AlertDialog(
          scrollable: true,
          shape: _profileDialogShape,
          titlePadding: const EdgeInsets.fromLTRB(24, 24, 24, 0),
          contentPadding: const EdgeInsets.fromLTRB(24, 18, 24, 8),
          actionsPadding: const EdgeInsets.fromLTRB(18, 8, 18, 18),
          title: const _ProfileDialogTitle(
            icon: Icons.logout_rounded,
            title: 'Log out?',
            accentColor: AppColors.error,
          ),
          content: Text(
            'You will need to log in again to access your account.',
            style: theme.textTheme.bodyMedium?.copyWith(height: 1.45),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.error,
                foregroundColor: AppColors.white,
              ),
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Log out'),
            ),
          ],
        );
      },
    );

    if (shouldLogout != true || !mounted) return;

    setState(() => _isSigningOut = true);

    try {
      await FirebaseAuth.instance.signOut();

      if (!mounted) return;

      Navigator.of(context).popUntil((route) => route.isFirst);
    } catch (_) {
      if (!mounted) return;

      setState(() => _isSigningOut = false);

      _showMessage('Unable to log out. Please try again.', isError: true);
    }
  }

  void _showMessage(String message, {bool isError = false}) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 4),
          margin: const EdgeInsets.all(18),
          backgroundColor: isError ? AppColors.error : AppColors.success,
          shape: const RoundedRectangleBorder(
            borderRadius: BorderRadius.all(Radius.circular(16)),
          ),
          content: Row(
            children: [
              Icon(
                isError
                    ? Icons.error_outline_rounded
                    : Icons.mark_email_read_rounded,
                color: AppColors.white,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  message,
                  style: const TextStyle(
                    color: AppColors.white,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
        ),
      );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final accountEmail = _profileEmail.isNotEmpty
        ? _profileEmail
        : FirebaseAuth.instance.currentUser?.email ?? 'No email available';
    final profileCompletionPercent = _profileCompletionPercent;
    final screenWidth = MediaQuery.sizeOf(context).width;
    final horizontalPadding = screenWidth < 360 ? 16.0 : 20.0;
    final textScale = MediaQuery.textScalerOf(context).scale(1.0);
    final formattedDateOfBirth = _formattedDateOfBirth(context);
    final heroTextScaleAdjustment = ((textScale - 1).clamp(0.0, 1.5) * 72)
        .toDouble();
    final heroExpandedHeight =
        (screenWidth < 360 ? 238.0 : 250.0) + heroTextScaleAdjustment;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      body: CustomScrollView(
        controller: _scrollController,
        keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
        slivers: [
          SliverAppBar(
            pinned: true,
            expandedHeight: heroExpandedHeight,
            toolbarHeight: 70,
            automaticallyImplyLeading: false,
            backgroundColor: colorScheme.primary,
            foregroundColor: colorScheme.onPrimary,
            surfaceTintColor: AppColors.transparent,
            elevation: 0,
            scrolledUnderElevation: 0,
            centerTitle: true,
            leadingWidth: 88,
            leading: Padding(
              padding: const EdgeInsets.only(left: 22),
              child: Align(
                alignment: Alignment.centerLeft,
                child: _ProfileBackButton(onPressed: _goBack),
              ),
            ),
            title: Text(
              'Profile',
              style: theme.textTheme.titleMedium?.copyWith(
                color: colorScheme.onPrimary,
                fontWeight: FontWeight.w700,
              ),
            ),
            shape: const RoundedRectangleBorder(
              borderRadius: BorderRadius.vertical(bottom: Radius.circular(28)),
            ),
            clipBehavior: Clip.antiAlias,
            flexibleSpace: FlexibleSpaceBar(
              collapseMode: CollapseMode.parallax,
              background: _ProfileSafePadding(
                padding: EdgeInsets.fromLTRB(
                  horizontalPadding,
                  72,
                  horizontalPadding,
                  22,
                ),
                includeTop: true,
                child: Align(
                  alignment: Alignment.bottomCenter,
                  child: _isLoadingProfile
                      ? const _ProfileHeroLoadingContent()
                      : Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              width: 74,
                              height: 74,
                              padding: const EdgeInsets.all(3),
                              decoration: BoxDecoration(
                                color: AppColors.white.withValues(alpha: 0.24),
                                shape: BoxShape.circle,
                              ),
                              child: DecoratedBox(
                                decoration: const BoxDecoration(
                                  color: AppColors.white,
                                  shape: BoxShape.circle,
                                ),
                                child: Center(
                                  child: ExcludeSemantics(
                                    child: Padding(
                                      padding: const EdgeInsets.all(14),
                                      child: FittedBox(
                                        fit: BoxFit.scaleDown,
                                        child: Text(
                                          _profileInitials,
                                          style: theme.textTheme.headlineSmall
                                              ?.copyWith(
                                                color: AppColors.primaryVariant,
                                                fontWeight: FontWeight.w800,
                                              ),
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                            const SizedBox(height: 10),
                            Text(
                              _fullName.isNotEmpty ? _fullName : 'Your profile',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              textAlign: TextAlign.center,
                              style: theme.textTheme.titleLarge?.copyWith(
                                color: colorScheme.onPrimary,
                                fontWeight: FontWeight.w800,
                                height: 1.12,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              accountEmail,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              textAlign: TextAlign.center,
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: colorScheme.onPrimary.withValues(
                                  alpha: 0.84,
                                ),
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ],
                        ),
                ),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 520),
                child: _ProfileSafePadding(
                  padding: EdgeInsets.fromLTRB(
                    horizontalPadding,
                    20,
                    horizontalPadding,
                    32,
                  ),
                  includeBottom: true,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (!_isLoadingProfile &&
                          profileCompletionPercent < 100) ...[
                        _ProfileCompletionBanner(
                          completionPercent: profileCompletionPercent,
                        ),
                        const SizedBox(height: 28),
                      ],
                      const _ProfileSectionLabel(
                        title: 'Personal details',
                        subtitle: 'Information used for bookings and support.',
                      ),
                      const SizedBox(height: 11),
                      if (_isLoadingProfile)
                        _ProfileSectionCard(
                          child: _ProfileDetailsSkeleton(
                            colorScheme: colorScheme,
                          ),
                        )
                      else
                        Form(
                          key: _profileFormKey,
                          child: Column(
                            children: [
                              _ProfileSectionCard(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 16,
                                ),
                                child: Column(
                                  children: [
                                    Row(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        const Padding(
                                          padding: EdgeInsets.only(top: 14),
                                          child: _ProfileLeadingIcon(
                                            icon: Icons.phone_outlined,
                                          ),
                                        ),
                                        const SizedBox(width: 12),
                                        Expanded(
                                          child: PhoneFormField(
                                            controller: _phoneController,
                                            enabled: !_isSavingProfile,
                                            autofillHints: const [
                                              AutofillHints.telephoneNumber,
                                            ],
                                            shouldLimitLengthByCountry: true,
                                            countryButtonStyle:
                                                const CountryButtonStyle(
                                                  borderRadius:
                                                      BorderRadius.all(
                                                        Radius.circular(12),
                                                      ),
                                                ),
                                            decoration: const InputDecoration(
                                              labelText: 'Phone number',
                                              hintText: 'Add phone number',
                                              filled: false,
                                              contentPadding:
                                                  EdgeInsets.symmetric(
                                                    vertical: 17,
                                                  ),
                                              border: InputBorder.none,
                                              enabledBorder: InputBorder.none,
                                              disabledBorder: InputBorder.none,
                                              focusedBorder: InputBorder.none,
                                              errorBorder: InputBorder.none,
                                              focusedErrorBorder:
                                                  InputBorder.none,
                                            ),
                                            validator: _validatePhoneNumber,
                                          ),
                                        ),
                                      ],
                                    ),
                                    const _ProfileSectionDivider(
                                      indent: 52,
                                      endIndent: 0,
                                    ),
                                    Semantics(
                                      button: true,
                                      enabled: !_isSavingProfile,
                                      label: 'Date of birth',
                                      value: formattedDateOfBirth,
                                      excludeSemantics: true,
                                      child: InkWell(
                                        onTap: _isSavingProfile
                                            ? null
                                            : _pickDateOfBirth,
                                        borderRadius: const BorderRadius.all(
                                          Radius.circular(16),
                                        ),
                                        child: Padding(
                                          padding: const EdgeInsets.symmetric(
                                            vertical: 14,
                                          ),
                                          child: Row(
                                            children: [
                                              const _ProfileLeadingIcon(
                                                icon: Icons
                                                    .calendar_today_outlined,
                                              ),
                                              const SizedBox(width: 12),
                                              Expanded(
                                                child: Column(
                                                  crossAxisAlignment:
                                                      CrossAxisAlignment.start,
                                                  children: [
                                                    Text(
                                                      'Date of birth',
                                                      style: theme
                                                          .textTheme
                                                          .bodySmall
                                                          ?.copyWith(
                                                            color: colorScheme
                                                                .onSurfaceVariant,
                                                          ),
                                                    ),
                                                    const SizedBox(height: 3),
                                                    Text(
                                                      formattedDateOfBirth,
                                                      style: theme
                                                          .textTheme
                                                          .bodyLarge
                                                          ?.copyWith(
                                                            color:
                                                                _dateOfBirth ==
                                                                    null
                                                                ? colorScheme
                                                                      .onSurfaceVariant
                                                                : colorScheme
                                                                      .onSurface,
                                                            fontWeight:
                                                                FontWeight.w600,
                                                          ),
                                                    ),
                                                  ],
                                                ),
                                              ),
                                              Icon(
                                                Icons.chevron_right_rounded,
                                                size: 22,
                                                color: colorScheme
                                                    .onSurfaceVariant,
                                              ),
                                            ],
                                          ),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              const SizedBox(height: 14),
                              FilledButton.icon(
                                onPressed: _isSavingProfile
                                    ? null
                                    : _saveProfileDetails,
                                icon: _isSavingProfile
                                    ? SizedBox.square(
                                        dimension: 20,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2.3,
                                          color: colorScheme.primary,
                                        ),
                                      )
                                    : const Icon(Icons.save_outlined),
                                label: Text(
                                  _isSavingProfile
                                      ? 'Saving profile...'
                                      : 'Save changes',
                                ),
                                style: FilledButton.styleFrom(
                                  minimumSize: const Size.fromHeight(54),
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 20,
                                    vertical: 15,
                                  ),
                                  shape: const RoundedRectangleBorder(
                                    borderRadius: BorderRadius.all(
                                      Radius.circular(17),
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      const SizedBox(height: 28),
                      const _ProfileSectionLabel(
                        title: 'Appearance',
                        subtitle: 'Choose how Trip Logic looks.',
                      ),
                      const SizedBox(height: 11),
                      _ProfileSectionCard(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          children: [
                            const Row(
                              children: [
                                _ProfileLeadingIcon(
                                  icon: Icons.palette_outlined,
                                ),
                                SizedBox(width: 12),
                                Expanded(
                                  child: _ProfileSettingSummary(
                                    title: 'App theme',
                                    subtitle:
                                        'Use your device setting or choose a mode.',
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 16),
                            _ThemeModePillSelector(
                              selectedMode: _selectedThemeMode,
                              onSelected: _setThemeMode,
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 28),
                      const _ProfileSectionLabel(
                        title: 'Account & security',
                        subtitle: 'Manage sign-in details and account access.',
                      ),
                      const SizedBox(height: 11),
                      _ProfileSectionCard(
                        padding: EdgeInsets.zero,
                        child: Column(
                          children: [
                            _ProfileActionRow(
                              icon: Icons.alternate_email_rounded,
                              title: 'Change email',
                              subtitle: accountEmail,
                              enabled:
                                  !_isSavingProfile &&
                                  !_isSendingReset &&
                                  !_isSigningOut,
                              iconColor: colorScheme.primary,
                              onTap: _showChangeEmailDialog,
                            ),
                            const _ProfileSectionDivider(),
                            _ProfileActionRow(
                              icon: Icons.lock_reset_rounded,
                              title: 'Reset password',
                              subtitle:
                                  'Send a reset link to your account email',
                              enabled: !_isSendingReset && !_isSigningOut,
                              isLoading: _isSendingReset,
                              iconColor: colorScheme.primary,
                              onTap: _showPasswordResetDialog,
                            ),
                            const _ProfileSectionDivider(),
                            _ProfileActionRow(
                              icon: Icons.logout_rounded,
                              title: 'Log out',
                              subtitle: 'Sign out of Trip Logic on this device',
                              enabled: !_isSigningOut && !_isSendingReset,
                              isLoading: _isSigningOut,
                              iconColor: AppColors.error,
                              onTap: _showLogoutDialog,
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProfileSafePadding extends StatelessWidget {
  const _ProfileSafePadding({
    required this.padding,
    required this.child,
    this.includeTop = false,
    this.includeBottom = false,
  });

  final EdgeInsets padding;
  final Widget child;
  final bool includeTop;
  final bool includeBottom;

  @override
  Widget build(BuildContext context) {
    final safePadding = MediaQuery.paddingOf(context);

    return Padding(
      padding: EdgeInsets.fromLTRB(
        padding.left,
        padding.top + (includeTop ? safePadding.top : 0),
        padding.right,
        padding.bottom + (includeBottom ? safePadding.bottom : 0),
      ),
      child: child,
    );
  }
}

class _ProfileBackButton extends StatelessWidget {
  const _ProfileBackButton({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final isDark = colorScheme.brightness == Brightness.dark;

    final materialColor = isDark
        ? AppColors.black.withValues(alpha: 0.24)
        : AppColors.white.withValues(alpha: 0.72);
    final borderColor = isDark
        ? AppColors.white.withValues(alpha: 0.22)
        : colorScheme.onSurface.withValues(alpha: 0.12);
    final iconColor = isDark ? AppColors.white : colorScheme.onSurface;

    return Tooltip(
      message: 'Back',
      child: Material(
        color: materialColor,
        shape: CircleBorder(side: BorderSide(color: borderColor)),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onPressed,
          customBorder: const CircleBorder(),
          child: SizedBox.square(
            dimension: 44,
            child: Icon(
              Icons.arrow_back_ios_new_rounded,
              size: 17,
              color: iconColor,
            ),
          ),
        ),
      ),
    );
  }
}

class _ProfileDialogTitle extends StatelessWidget {
  const _ProfileDialogTitle({
    required this.icon,
    required this.title,
    this.accentColor,
  });

  final IconData icon;
  final String title;
  final Color? accentColor;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final resolvedAccentColor = accentColor ?? colorScheme.primary;

    return Row(
      children: [
        Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(
            color: resolvedAccentColor.withValues(alpha: 0.11),
            borderRadius: const BorderRadius.all(Radius.circular(14)),
          ),
          child: Icon(icon, color: resolvedAccentColor),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Text(
            title,
            style: theme.textTheme.titleLarge?.copyWith(
              fontWeight: FontWeight.w800,
            ),
          ),
        ),
      ],
    );
  }
}

class _ProfileSectionLabel extends StatelessWidget {
  const _ProfileSectionLabel({required this.title, required this.subtitle});

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title.toUpperCase(),
            style: theme.textTheme.labelLarge?.copyWith(
              color: colorScheme.onSurface,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.8,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            subtitle,
            style: theme.textTheme.bodySmall?.copyWith(
              color: colorScheme.onSurfaceVariant,
              height: 1.35,
            ),
          ),
        ],
      ),
    );
  }
}

class _ProfileLeadingIcon extends StatelessWidget {
  const _ProfileLeadingIcon({required this.icon});

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Container(
      width: 40,
      height: 40,
      decoration: BoxDecoration(
        color: colorScheme.primary.withValues(alpha: 0.09),
        shape: BoxShape.circle,
      ),
      child: Icon(icon, size: 20, color: colorScheme.primary),
    );
  }
}

class _ProfileSettingSummary extends StatelessWidget {
  const _ProfileSettingSummary({required this.title, required this.subtitle});

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: theme.textTheme.bodyLarge?.copyWith(
            color: colorScheme.onSurface,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 3),
        Text(
          subtitle,
          style: theme.textTheme.bodySmall?.copyWith(
            color: colorScheme.onSurfaceVariant,
            height: 1.35,
          ),
        ),
      ],
    );
  }
}

class _ProfileCompletionBanner extends StatelessWidget {
  const _ProfileCompletionBanner({required this.completionPercent});

  final int completionPercent;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerLow,
        borderRadius: const BorderRadius.all(Radius.circular(20)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: colorScheme.primary,
              shape: BoxShape.circle,
            ),
            child: Icon(
              Icons.fact_check_outlined,
              size: 21,
              color: colorScheme.onPrimary,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        'Profile completion',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: colorScheme.onSurface,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                    Text(
                      '$completionPercent%',
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: colorScheme.primary,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 7),
                ClipRRect(
                  borderRadius: const BorderRadius.all(Radius.circular(999)),
                  child: LinearProgressIndicator(
                    value: completionPercent / 100,
                    minHeight: 6,
                    backgroundColor: colorScheme.onSurface.withValues(
                      alpha: 0.1,
                    ),
                    color: colorScheme.primary,
                  ),
                ),
                const SizedBox(height: 7),
                Text(
                  'Add the remaining details for smoother bookings.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: colorScheme.onSurfaceVariant,
                    height: 1.35,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ProfileSectionCard extends StatelessWidget {
  const _ProfileSectionCard({required this.child, this.padding});

  final Widget child;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return SizedBox(
      width: double.infinity,
      child: Material(
        color: colorScheme.surfaceContainerLow,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(20)),
        ),
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: padding ?? const EdgeInsets.all(16),
          child: child,
        ),
      ),
    );
  }
}

class _ProfileActionRow extends StatelessWidget {
  const _ProfileActionRow({
    required this.icon,
    required this.title,
    required this.onTap,
    required this.enabled,
    this.subtitle,
    this.isLoading = false,
    this.iconColor,
  });

  final IconData icon;
  final String title;
  final VoidCallback onTap;
  final bool enabled;
  final String? subtitle;
  final bool isLoading;
  final Color? iconColor;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Semantics(
      button: true,
      enabled: enabled,
      label: title,
      value: subtitle,
      excludeSemantics: true,
      child: Opacity(
        opacity: enabled || isLoading ? 1 : 0.55,
        child: Material(
          color: AppColors.transparent,
          child: InkWell(
            onTap: enabled ? onTap : null,
            borderRadius: const BorderRadius.all(Radius.circular(20)),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              child: Row(
                children: [
                  Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: (iconColor ?? colorScheme.primary).withValues(
                        alpha: 0.1,
                      ),
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      icon,
                      size: 20,
                      color: iconColor ?? colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          style: theme.textTheme.bodyLarge?.copyWith(
                            fontWeight: FontWeight.w600,
                            fontSize: 15,
                          ),
                        ),
                        if (subtitle != null) ...[
                          const SizedBox(height: 3),
                          Text(
                            subtitle!,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(width: 12),
                  if (isLoading)
                    SizedBox.square(
                      dimension: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.2,
                        color: iconColor ?? colorScheme.primary,
                      ),
                    )
                  else
                    Icon(
                      Icons.chevron_right_rounded,
                      color: colorScheme.onSurfaceVariant,
                      size: 22,
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ThemeModePillSelector extends StatelessWidget {
  const _ThemeModePillSelector({
    required this.selectedMode,
    required this.onSelected,
  });

  final ThemeMode selectedMode;
  final ValueChanged<ThemeMode> onSelected;

  static const _options = [ThemeMode.system, ThemeMode.light, ThemeMode.dark];

  static Alignment _alignmentForMode(ThemeMode mode) => switch (mode) {
    ThemeMode.system => Alignment.centerLeft,
    ThemeMode.light => Alignment.center,
    ThemeMode.dark => Alignment.centerRight,
  };

  static String _themeModeLabel(ThemeMode mode) => switch (mode) {
    ThemeMode.light => 'Light',
    ThemeMode.dark => 'Dark',
    ThemeMode.system => 'Device',
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 56),
      child: Material(
        color: colorScheme.surfaceContainerHighest,
        borderRadius: const BorderRadius.all(Radius.circular(17)),
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsets.all(5),
          child: Stack(
            children: [
              Positioned.fill(
                child: AnimatedAlign(
                  duration: const Duration(milliseconds: 280),
                  curve: Curves.easeInOutCubic,
                  alignment: _alignmentForMode(selectedMode),
                  child: FractionallySizedBox(
                    widthFactor: 1 / 3,
                    heightFactor: 1,
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: colorScheme.primary,
                        borderRadius: const BorderRadius.all(
                          Radius.circular(13),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              Row(
                children: _options.map((mode) {
                  final isSelected = selectedMode == mode;
                  final label = _themeModeLabel(mode);

                  return Expanded(
                    child: Semantics(
                      button: true,
                      selected: isSelected,
                      label: label,
                      excludeSemantics: true,
                      child: Material(
                        color: AppColors.transparent,
                        child: InkWell(
                          onTap: () => onSelected(mode),
                          borderRadius: const BorderRadius.all(
                            Radius.circular(13),
                          ),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 4,
                              vertical: 11,
                            ),
                            child: Center(
                              child: FittedBox(
                                fit: BoxFit.scaleDown,
                                child: Text(
                                  label,
                                  maxLines: 1,
                                  style: theme.textTheme.bodyMedium?.copyWith(
                                    color: isSelected
                                        ? colorScheme.onPrimary
                                        : colorScheme.onSurfaceVariant,
                                    fontWeight: isSelected
                                        ? FontWeight.w700
                                        : FontWeight.w600,
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ProfileDetailsSkeleton extends StatelessWidget {
  const _ProfileDetailsSkeleton({required this.colorScheme});

  final ColorScheme colorScheme;

  @override
  Widget build(BuildContext context) {
    final baseColor = colorScheme.surfaceContainerHighest;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: baseColor,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    height: 14,
                    width: 120,
                    decoration: BoxDecoration(
                      color: baseColor,
                      borderRadius: const BorderRadius.all(Radius.circular(8)),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Container(
                    height: 12,
                    width: 190,
                    decoration: BoxDecoration(
                      color: baseColor,
                      borderRadius: const BorderRadius.all(Radius.circular(8)),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        Divider(height: 1, color: colorScheme.outlineVariant),
        const SizedBox(height: 16),
        Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: baseColor,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    height: 14,
                    width: 110,
                    decoration: BoxDecoration(
                      color: baseColor,
                      borderRadius: const BorderRadius.all(Radius.circular(8)),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Container(
                    height: 12,
                    width: 150,
                    decoration: BoxDecoration(
                      color: baseColor,
                      borderRadius: const BorderRadius.all(Radius.circular(8)),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _ProfileHeroLoadingContent extends StatelessWidget {
  const _ProfileHeroLoadingContent();

  @override
  Widget build(BuildContext context) {
    final baseColor = AppColors.white.withValues(alpha: 0.22);

    return Semantics(
      liveRegion: true,
      label: 'Loading profile',
      excludeSemantics: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 74,
            height: 74,
            decoration: BoxDecoration(color: baseColor, shape: BoxShape.circle),
          ),
          const SizedBox(height: 10),
          Container(
            height: 18,
            width: 150,
            decoration: BoxDecoration(
              color: baseColor,
              borderRadius: const BorderRadius.all(Radius.circular(9)),
            ),
          ),
          const SizedBox(height: 7),
          Container(
            height: 12,
            width: 125,
            decoration: BoxDecoration(
              color: baseColor,
              borderRadius: const BorderRadius.all(Radius.circular(8)),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProfileSectionDivider extends StatelessWidget {
  const _ProfileSectionDivider({this.indent = 64, this.endIndent = 16});

  final double indent;
  final double endIndent;

  @override
  Widget build(BuildContext context) {
    return Divider(
      height: 1,
      thickness: 1,
      indent: indent,
      endIndent: endIndent,
      color: Theme.of(
        context,
      ).colorScheme.outlineVariant.withValues(alpha: 0.72),
    );
  }
}
