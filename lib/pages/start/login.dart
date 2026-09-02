import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:trip_logic/pages/start/register.dart';
import 'package:trip_logic/pages/start/splash.dart';
import 'package:trip_logic/theme/app_colors.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  static final _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  final _isPasswordVisible = ValueNotifier(false);
  final _isLoading = ValueNotifier(false);

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _isPasswordVisible.dispose();
    _isLoading.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    FocusScope.of(context, createDependency: false).unfocus();

    final email = _emailController.text.trim();
    final password = _passwordController.text;

    if (email.isEmpty) {
      _showMessage('Enter your email address.');
      return;
    }

    if (!_isValidEmail(email)) {
      _showMessage('Enter a valid email address.');
      return;
    }

    if (password.isEmpty) {
      _showMessage('Enter your password.');
      return;
    }

    _isLoading.value = true;

    try {
      final credential = await FirebaseAuth.instance.signInWithEmailAndPassword(
        email: email,
        password: password,
      );

      await credential.user?.getIdToken(true);

      if (!mounted) return;

      _isLoading.value = false;
      _showSuccessMessage(
        'Login successful. Welcome back!',
        const Duration(seconds: 3),
      );
      Navigator.of(context).popUntil((route) => route.isFirst);
    } catch (error) {
      if (!mounted) return;

      _isLoading.value = false;
      _showMessage(
        error is FirebaseAuthException
            ? _firebaseErrorMessage(error)
            : 'Something went wrong. Please try again.',
      );
    }
  }

  Future<void> _showPasswordResetDialog() {
    var resetEmail = _emailController.text.trim();
    final formKey = GlobalKey<FormState>();
    bool isSending = false;
    String? requestError;

    return showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        return StatefulBuilder(
          builder: (statefulDialogContext, setDialogState) {
            Future<void> sendResetEmail() async {
              if (isSending) return;

              final formState = formKey.currentState;
              if (formState == null || !formState.validate()) return;

              formState.save();
              final email = resetEmail;

              setDialogState(() {
                isSending = true;
                requestError = null;
              });

              var successMessage =
                  'Password reset email sent. Check your inbox and spam folder.';

              try {
                await FirebaseAuth.instance.sendPasswordResetEmail(
                  email: email,
                );
              } on FirebaseAuthException catch (error) {
                if (error.code == 'user-not-found') {
                  successMessage =
                      'If an account is connected to this email, a password reset link has been sent.';
                } else {
                  if (!dialogContext.mounted) return;

                  setDialogState(() {
                    isSending = false;
                    requestError = _passwordResetErrorMessage(error);
                  });
                  return;
                }
              } catch (_) {
                if (!dialogContext.mounted) return;

                setDialogState(() {
                  isSending = false;
                  requestError = 'Something went wrong. Please try again.';
                });
                return;
              }

              if (!dialogContext.mounted) return;

              Navigator.of(dialogContext).pop();

              if (!mounted) return;

              _emailController.text = email;
              _showSuccessMessage(successMessage);
            }

            final theme = Theme.of(statefulDialogContext);
            final colorScheme = theme.colorScheme;
            const resetBorder = OutlineInputBorder(
              borderRadius: BorderRadius.all(Radius.circular(16)),
              borderSide: BorderSide.none,
            );

            return AlertDialog(
              scrollable: true,
              shape: const RoundedRectangleBorder(
                borderRadius: BorderRadius.all(Radius.circular(24)),
              ),
              titlePadding: const EdgeInsets.fromLTRB(24, 24, 24, 0),
              contentPadding: const EdgeInsets.fromLTRB(24, 18, 24, 8),
              actionsPadding: const EdgeInsets.fromLTRB(18, 8, 18, 18),
              title: Row(
                children: [
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      color: colorScheme.primary.withValues(alpha: 0.11),
                      borderRadius: const BorderRadius.all(Radius.circular(14)),
                    ),
                    child: Icon(
                      Icons.lock_reset_rounded,
                      color: colorScheme.primary,
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Text(
                      'Reset password',
                      style: theme.textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                ],
              ),
              content: Form(
                key: formKey,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Enter the email address related to your account. '
                      'We will send you a link to create a new password.',
                      style: theme.textTheme.bodyMedium?.copyWith(height: 1.45),
                    ),
                    const SizedBox(height: 20),
                    TextFormField(
                      initialValue: resetEmail,
                      enabled: !isSending,
                      autofocus: true,
                      keyboardType: TextInputType.emailAddress,
                      textInputAction: TextInputAction.done,
                      autocorrect: false,
                      enableSuggestions: false,
                      onSaved: (value) => resetEmail = value?.trim() ?? '',
                      onFieldSubmitted: (_) => sendResetEmail(),
                      validator: (value) {
                        final email = value?.trim() ?? '';

                        if (email.isEmpty) {
                          return 'Enter your email address.';
                        }

                        if (!_isValidEmail(email)) {
                          return 'Enter a valid email address.';
                        }

                        return null;
                      },
                      decoration: InputDecoration(
                        labelText: 'Account email',
                        hintText: 'you@example.com',
                        prefixIcon: const Icon(Icons.mail_outline_rounded),
                        filled: true,
                        fillColor: colorScheme.surfaceContainerLow,
                        border: resetBorder,
                        focusedBorder: OutlineInputBorder(
                          borderRadius: resetBorder.borderRadius,
                          borderSide: BorderSide(
                            color: colorScheme.primary,
                            width: 1.5,
                          ),
                        ),
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
                  onPressed: isSending
                      ? null
                      : () => Navigator.of(dialogContext).pop(),
                  child: const Text('Cancel'),
                ),
                FilledButton(
                  onPressed: isSending ? null : sendResetEmail,
                  child: isSending
                      ? SizedBox.square(
                          dimension: 19,
                          child: CircularProgressIndicator(
                            strokeWidth: 2.3,
                            color: colorScheme.onPrimary,
                          ),
                        )
                      : const Text('Send reset link'),
                ),
              ],
            );
          },
        );
      },
    );
  }

  static String _firebaseErrorMessage(
    FirebaseAuthException error,
  ) => switch (error.code) {
    'invalid-email' => 'Enter a valid email address.',
    'invalid-credential' ||
    'user-not-found' ||
    'wrong-password' => 'The email or password is incorrect.',
    'user-disabled' => 'This account has been disabled.',
    'too-many-requests' => 'Too many login attempts. Please try again later.',
    'network-request-failed' => 'Check your internet connection and try again.',
    _ => error.message ?? 'Unable to log in. Please try again.',
  };

  static String _passwordResetErrorMessage(FirebaseAuthException error) =>
      switch (error.code) {
        'invalid-email' => 'Enter a valid email address.',
        'missing-email' => 'Enter your email address.',
        'too-many-requests' =>
          'Too many requests. Please wait and try again later.',
        'network-request-failed' =>
          'Check your internet connection and try again.',
        'operation-not-allowed' => 'Password reset is not currently available.',
        _ => error.message ?? 'Unable to send the password reset email.',
      };

  void _showSnackBar(
    String message,
    Color backgroundColor,
    Icon icon, [
    Duration duration = const Duration(seconds: 4),
  ]) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          behavior: SnackBarBehavior.floating,
          duration: duration,
          margin: const EdgeInsets.all(18),
          backgroundColor: backgroundColor,
          shape: const RoundedRectangleBorder(
            borderRadius: BorderRadius.all(Radius.circular(16)),
          ),
          content: Row(
            children: [
              icon,
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

  void _showMessage(String message) {
    _showSnackBar(
      message,
      AppColors.error,
      const Icon(Icons.error_outline_rounded, color: AppColors.white),
    );
  }

  void _showSuccessMessage(
    String message, [
    Duration duration = const Duration(seconds: 4),
  ]) {
    _showSnackBar(
      message,
      AppColors.success,
      const Icon(Icons.mark_email_read_rounded, color: AppColors.white),
      duration,
    );
  }

  void _goBack() {
    Navigator.of(context).pushAndRemoveUntil(
      _noTransitionRoute(const SplashIntroPage()),
      (route) => false,
    );
  }

  void _openRegister() {
    Navigator.of(context).push(_noTransitionRoute(const RegisterPage()));
  }

  void _togglePasswordVisibility() {
    _isPasswordVisible.value = !_isPasswordVisible.value;
  }

  void _submitPassword(String _) {
    if (!_isLoading.value) _login();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final isDark = colorScheme.brightness == Brightness.dark;
    final panel = _LoginPanel(
      emailController: _emailController,
      passwordController: _passwordController,
      passwordVisibility: _isPasswordVisible,
      loading: _isLoading,
      onTogglePasswordVisibility: _togglePasswordVisibility,
      onPasswordSubmitted: _submitPassword,
      onForgotPassword: _showPasswordResetDialog,
      onLogin: _login,
      onRegister: _openRegister,
    );
    final expandedHero = _LoginHero(compact: false, onBack: _goBack);
    final compactHero = _LoginHero(compact: true, onBack: _goBack);

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle(
        statusBarColor: AppColors.transparent,
        statusBarBrightness: Brightness.dark,
        statusBarIconBrightness: Brightness.light,
        systemNavigationBarColor: colorScheme.surface,
        systemNavigationBarIconBrightness: isDark
            ? Brightness.light
            : Brightness.dark,
        systemNavigationBarDividerColor: AppColors.transparent,
        systemStatusBarContrastEnforced: false,
        systemNavigationBarContrastEnforced: false,
      ),
      child: Builder(
        builder: (keyboardContext) {
          final keyboardVisible =
              MediaQuery.viewInsetsOf(keyboardContext).bottom > 0;
          final topPadding = MediaQuery.paddingOf(keyboardContext).top;

          return Scaffold(
            backgroundColor: colorScheme.surface,
            body: LayoutBuilder(
              builder: (_, constraints) {
                final screenHeight = constraints.maxHeight;
                final preferredHeroHeight = keyboardVisible
                    ? topPadding + 102
                    : (screenHeight * 0.38).clamp(250.0, 310.0).toDouble();
                final heroHeight = preferredHeroHeight
                    .clamp(0.0, screenHeight)
                    .toDouble();
                final panelTop = (heroHeight - 34).clamp(0.0, screenHeight);

                return Stack(
                  children: [
                    Positioned(
                      top: 0,
                      left: 0,
                      right: 0,
                      height: heroHeight,
                      child: keyboardVisible ? compactHero : expandedHero,
                    ),
                    Positioned.fill(top: panelTop, child: panel),
                  ],
                );
              },
            ),
          );
        },
      ),
    );
  }

  static bool _isValidEmail(String email) => _emailPattern.hasMatch(email);

  static PageRouteBuilder<T> _noTransitionRoute<T>(Widget page) =>
      PageRouteBuilder<T>(
        pageBuilder: (_, _, _) => page,
        transitionDuration: Duration.zero,
        reverseTransitionDuration: Duration.zero,
      );

  static InputDecoration _inputDecoration({
    required BuildContext context,
    required String hintText,
    required IconData icon,
    Widget? suffixIcon,
  }) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    const borderRadius = BorderRadius.all(Radius.circular(17));
    const border = OutlineInputBorder(
      borderRadius: borderRadius,
      borderSide: BorderSide.none,
    );

    return InputDecoration(
      hintText: hintText,
      prefixIcon: Icon(
        icon,
        size: 20,
        color: colorScheme.primary.withValues(alpha: 0.88),
      ),
      suffixIcon: suffixIcon,
      filled: true,
      fillColor: colorScheme.surfaceContainerLow,
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 19),
      hintStyle: theme.textTheme.bodyMedium?.copyWith(
        color: colorScheme.onSurfaceVariant,
        fontSize: 14,
      ),
      border: border,
      focusedBorder: OutlineInputBorder(
        borderRadius: borderRadius,
        borderSide: BorderSide(color: colorScheme.primary, width: 1.5),
      ),
    );
  }
}

class _LoginPanel extends StatelessWidget {
  const _LoginPanel({
    required this.emailController,
    required this.passwordController,
    required this.passwordVisibility,
    required this.loading,
    required this.onTogglePasswordVisibility,
    required this.onPasswordSubmitted,
    required this.onForgotPassword,
    required this.onLogin,
    required this.onRegister,
  });

  final TextEditingController emailController;
  final TextEditingController passwordController;
  final ValueNotifier<bool> passwordVisibility;
  final ValueNotifier<bool> loading;
  final VoidCallback onTogglePasswordVisibility;
  final ValueChanged<String> onPasswordSubmitted;
  final VoidCallback onForgotPassword;
  final VoidCallback onLogin;
  final VoidCallback onRegister;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final isDark = colorScheme.brightness == Brightness.dark;
    final dividerColor = colorScheme.outlineVariant.withValues(alpha: 0.75);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: colorScheme.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(34)),
        boxShadow: [
          BoxShadow(
            color: colorScheme.shadow.withValues(alpha: isDark ? 0.30 : 0.14),
            blurRadius: 34,
            spreadRadius: -10,
            offset: const Offset(0, -8),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: const BorderRadius.vertical(top: Radius.circular(34)),
        child: SafeArea(
          top: false,
          child: SingleChildScrollView(
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            padding: const EdgeInsets.fromLTRB(24, 30, 24, 26),
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 460),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _LoginRegisterPill(onRegisterTap: onRegister),
                    const SizedBox(height: 24),
                    Text(
                      'Sign in to your account',
                      style: theme.textTheme.titleLarge?.copyWith(
                        color: colorScheme.onSurface,
                        fontSize: 24,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.45,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Enter your details below to continue.',
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: colorScheme.onSurfaceVariant,
                        fontSize: 14,
                        height: 1.45,
                      ),
                    ),
                    const SizedBox(height: 24),
                    TextField(
                      controller: emailController,
                      autocorrect: false,
                      enableSuggestions: false,
                      keyboardType: TextInputType.emailAddress,
                      textInputAction: TextInputAction.next,
                      decoration: _LoginPageState._inputDecoration(
                        context: context,
                        hintText: 'Enter email',
                        icon: Icons.mail_outline_rounded,
                      ),
                    ),
                    const SizedBox(height: 14),
                    ValueListenableBuilder<bool>(
                      valueListenable: passwordVisibility,
                      builder: (fieldContext, isVisible, _) => TextField(
                        controller: passwordController,
                        obscureText: !isVisible,
                        autocorrect: false,
                        enableSuggestions: false,
                        textInputAction: TextInputAction.done,
                        onSubmitted: onPasswordSubmitted,
                        decoration: _LoginPageState._inputDecoration(
                          context: fieldContext,
                          hintText: 'Password',
                          icon: Icons.lock_outline_rounded,
                          suffixIcon: IconButton(
                            tooltip: isVisible
                                ? 'Hide password'
                                : 'Show password',
                            onPressed: onTogglePasswordVisibility,
                            icon: Icon(
                              isVisible
                                  ? Icons.visibility_outlined
                                  : Icons.visibility_off_outlined,
                              size: 20,
                            ),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    ValueListenableBuilder<bool>(
                      valueListenable: loading,
                      builder: (_, isLoading, _) => _SessionActions(
                        enabled: !isLoading,
                        onForgotPassword: onForgotPassword,
                      ),
                    ),
                    const SizedBox(height: 22),
                    SizedBox(
                      width: double.infinity,
                      height: 57,
                      child: ValueListenableBuilder<bool>(
                        valueListenable: loading,
                        builder: (_, isLoading, _) => FilledButton(
                          onPressed: isLoading ? null : onLogin,
                          style: FilledButton.styleFrom(
                            backgroundColor: colorScheme.primary,
                            foregroundColor: colorScheme.onPrimary,
                            disabledBackgroundColor: colorScheme.primary
                                .withValues(alpha: 0.75),
                            disabledForegroundColor: colorScheme.onPrimary,
                            shape: const RoundedRectangleBorder(
                              borderRadius: BorderRadius.all(
                                Radius.circular(17),
                              ),
                            ),
                          ),
                          child: isLoading
                              ? SizedBox.square(
                                  dimension: 23,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2.5,
                                    color: colorScheme.onPrimary,
                                  ),
                                )
                              : const Text(
                                  'Login',
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.w700,
                                    letterSpacing: 0.1,
                                  ),
                                ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 26),
                    Row(
                      children: [
                        Expanded(child: Divider(color: dividerColor)),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 14),
                          child: Text(
                            'Or login with',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: colorScheme.onSurfaceVariant,
                              fontSize: 13,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                        Expanded(child: Divider(color: dividerColor)),
                      ],
                    ),
                    const SizedBox(height: 18),
                    const _SocialLoginOptions(),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _LoginHero extends StatelessWidget {
  const _LoginHero({required this.compact, required this.onBack});

  static final _background = Image.asset(
    'lib/assets/images/startup/bg.webp',
    fit: BoxFit.cover,
    alignment: Alignment.topCenter,
    filterQuality: FilterQuality.high,
    excludeFromSemantics: true,
  );
  static final _overlay = DecoratedBox(
    decoration: BoxDecoration(
      gradient: LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [
          AppColors.black.withValues(alpha: 0.10),
          AppColors.primaryVariant.withValues(alpha: 0.54),
        ],
      ),
    ),
  );

  final bool compact;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Stack(
      fit: StackFit.expand,
      children: [
        _background,
        _overlay,
        SafeArea(
          bottom: false,
          child: Padding(
            padding: EdgeInsets.fromLTRB(22, 14, 22, compact ? 24 : 54),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    _BackButton(onPressed: onBack),
                    const Spacer(),
                    const _AuthBrandBadge(),
                  ],
                ),
                if (!compact) ...[
                  const SizedBox(height: 12),
                  Expanded(
                    child: LayoutBuilder(
                      builder: (_, constraints) => Align(
                        alignment: Alignment.bottomLeft,
                        child: FittedBox(
                          fit: BoxFit.scaleDown,
                          alignment: Alignment.bottomLeft,
                          child: SizedBox(
                            width: constraints.maxWidth,
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Welcome\nBack',
                                  style: theme.textTheme.headlineLarge
                                      ?.copyWith(
                                        color: AppColors.white,
                                        fontSize: 34,
                                        height: 1.02,
                                        fontWeight: FontWeight.w800,
                                        letterSpacing: -0.8,
                                      ),
                                ),
                                const SizedBox(height: 7),
                                Text(
                                  'Sign in to continue planning your next trip.',
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: theme.textTheme.bodyMedium?.copyWith(
                                    color: AppColors.white.withValues(
                                      alpha: 0.88,
                                    ),
                                    fontSize: 14,
                                    height: 1.4,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _AuthBrandBadge extends StatelessWidget {
  const _AuthBrandBadge();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final isDark = colorScheme.brightness == Brightness.dark;

    final containerColor = isDark
        ? AppColors.black.withValues(alpha: 0.22)
        : AppColors.white.withValues(alpha: 0.72);
    final containerBorderColor = isDark
        ? AppColors.white.withValues(alpha: 0.22)
        : colorScheme.onSurface.withValues(alpha: 0.12);
    final innerCircleColor = isDark
        ? AppColors.white.withValues(alpha: 0.14)
        : colorScheme.onSurface.withValues(alpha: 0.10);
    final foregroundColor = isDark ? AppColors.white : colorScheme.onSurface;

    return Semantics(
      label: 'Trip Logic sign in',
      child: Container(
        height: 42,
        padding: const EdgeInsets.fromLTRB(5, 5, 14, 5),
        decoration: BoxDecoration(
          color: containerColor,
          borderRadius: const BorderRadius.all(Radius.circular(24)),
          border: Border.all(color: containerBorderColor),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: innerCircleColor,
              ),
              child: Icon(
                Icons.login_rounded,
                size: 18,
                color: foregroundColor,
              ),
            ),
            const SizedBox(width: 9),
            ExcludeSemantics(
              child: Text(
                'SIGN IN',
                style: theme.textTheme.labelSmall?.copyWith(
                  color: foregroundColor,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0.9,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BackButton extends StatelessWidget {
  const _BackButton({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
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

class _SessionActions extends StatelessWidget {
  const _SessionActions({
    required this.enabled,
    required this.onForgotPassword,
  });

  final bool enabled;
  final VoidCallback onForgotPassword;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final textScale = MediaQuery.textScalerOf(context).scale(1);
    final staySignedIn = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.check_circle_rounded, size: 21, color: colorScheme.primary),
        const SizedBox(width: 9),
        Flexible(
          child: Text(
            'Stay signed in',
            style: theme.textTheme.bodySmall?.copyWith(
              color: colorScheme.onSurfaceVariant,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ],
    );
    final forgotPassword = TextButton(
      onPressed: enabled ? onForgotPassword : null,
      style: TextButton.styleFrom(
        foregroundColor: colorScheme.primary,
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
        minimumSize: const Size(48, 44),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
      child: const Text(
        'Forgot password?',
        style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
      ),
    );

    return LayoutBuilder(
      builder: (_, constraints) {
        final stackActions = constraints.maxWidth < 360 || textScale > 1.2;

        if (stackActions) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              staySignedIn,
              const SizedBox(height: 2),
              Align(alignment: Alignment.centerRight, child: forgotPassword),
            ],
          );
        }

        return Row(
          children: [
            Expanded(child: staySignedIn),
            const SizedBox(width: 10),
            forgotPassword,
          ],
        );
      },
    );
  }
}

class _LoginRegisterPill extends StatelessWidget {
  const _LoginRegisterPill({required this.onRegisterTap});

  final VoidCallback onRegisterTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final textScale = MediaQuery.textScalerOf(context).scale(1);
    final extraHeight = ((textScale - 1) * 24).clamp(0.0, 42.0).toDouble();

    return Container(
      height: 60 + extraHeight,
      padding: const EdgeInsets.all(5),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerLow,
        borderRadius: const BorderRadius.all(Radius.circular(20)),
        border: Border.all(
          color: colorScheme.outlineVariant.withValues(alpha: 0.58),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Semantics(
              selected: true,
              child: Container(
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: colorScheme.primary,
                  borderRadius: const BorderRadius.all(Radius.circular(15)),
                  boxShadow: [
                    BoxShadow(
                      color: colorScheme.primary.withValues(alpha: 0.20),
                      blurRadius: 14,
                      spreadRadius: -5,
                      offset: const Offset(0, 6),
                    ),
                  ],
                ),
                child: Text(
                  'Login',
                  style: theme.textTheme.titleSmall?.copyWith(
                    color: colorScheme.onPrimary,
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ),
          ),
          Expanded(
            child: Semantics(
              button: true,
              selected: false,
              child: InkWell(
                onTap: onRegisterTap,
                borderRadius: const BorderRadius.all(Radius.circular(15)),
                child: Center(
                  child: Text(
                    'Register',
                    style: theme.textTheme.titleSmall?.copyWith(
                      color: colorScheme.onSurfaceVariant,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
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

class _SocialLoginOptions extends StatelessWidget {
  const _SocialLoginOptions();

  @override
  Widget build(BuildContext context) {
    final textScale = MediaQuery.textScalerOf(context).scale(1);
    final google = _SocialButton(
      label: 'Google',
      icon: SvgPicture.asset(
        'lib/assets/images/startup/icons8-google.svg',
        width: 20,
        height: 20,
      ),
    );
    final facebook = _SocialButton(
      label: 'Facebook',
      icon: SvgPicture.asset(
        'lib/assets/images/startup/icons8-facebook.svg',
        width: 20,
        height: 20,
      ),
    );

    return LayoutBuilder(
      builder: (_, constraints) {
        final stackOptions = constraints.maxWidth < 360 || textScale > 1.2;

        if (stackOptions) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [google, const SizedBox(height: 12), facebook],
          );
        }

        return Row(
          children: [
            Expanded(child: google),
            const SizedBox(width: 14),
            Expanded(child: facebook),
          ],
        );
      },
    );
  }
}

class _SocialButton extends StatelessWidget {
  const _SocialButton({required this.label, required this.icon});

  final String label;
  final Widget icon;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final textScale = MediaQuery.textScalerOf(context).scale(1);
    final extraHeight = ((textScale - 1) * 18).clamp(0.0, 30.0).toDouble();

    return Container(
      height: 54 + extraHeight,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerLow,
        borderRadius: const BorderRadius.all(Radius.circular(17)),
        border: Border.all(
          color: colorScheme.outlineVariant.withValues(alpha: 0.58),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          icon,
          const SizedBox(width: 9),
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.titleSmall?.copyWith(
                color: colorScheme.onSurface,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
