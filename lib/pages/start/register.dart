import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:trip_logic/pages/main/home.dart';
import 'package:trip_logic/pages/start/login.dart';
import 'package:trip_logic/pages/start/splash.dart';
import 'package:trip_logic/theme/app_colors.dart';

class RegisterPage extends StatefulWidget {
  const RegisterPage({super.key});

  @override
  State<RegisterPage> createState() => _RegisterPageState();
}

class _RegisterPageState extends State<RegisterPage> {
  static final _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  final TextEditingController _confirmPasswordController =
      TextEditingController();

  final _showPassword = ValueNotifier(false);
  final _showConfirmPassword = ValueNotifier(false);
  final _isLoading = ValueNotifier(false);

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    _showPassword.dispose();
    _showConfirmPassword.dispose();
    _isLoading.dispose();
    super.dispose();
  }

  Future<void> _register() async {
    if (_isLoading.value) return;

    FocusScope.of(context, createDependency: false).unfocus();

    final fullName = _nameController.text.trim();
    final email = _emailController.text.trim();
    final password = _passwordController.text;
    final confirmPassword = _confirmPasswordController.text;

    if (fullName.length < 2) {
      _showError('Enter your full name.');
      return;
    }

    if (!_emailPattern.hasMatch(email)) {
      _showError('Enter a valid email address.');
      return;
    }

    if (password.length < 6) {
      _showError('Your password must contain at least 6 characters.');
      return;
    }

    if (password != confirmPassword) {
      _showError('The passwords do not match.');
      return;
    }

    _isLoading.value = true;

    try {
      final credential = await FirebaseAuth.instance
          .createUserWithEmailAndPassword(email: email, password: password);

      final user = credential.user;

      if (user == null) {
        throw Exception('Firebase did not create the account.');
      }

      try {
        await user.updateDisplayName(fullName);
        await user.getIdToken(true);
      } catch (_) {}

      try {
        await FirebaseFirestore.instance.collection('users').doc(user.uid).set({
          'uid': user.uid,
          'fullName': fullName,
          'email': user.email ?? email,
          'createdAt': FieldValue.serverTimestamp(),
          'updatedAt': FieldValue.serverTimestamp(),
        });
      } on FirebaseException {
        try {
          await user.delete();
        } catch (_) {}
        rethrow;
      }

      bool verificationSent = false;
      try {
        await user.sendEmailVerification();
        verificationSent = true;
      } catch (_) {}

      if (!mounted) return;

      _isLoading.value = false;
      _showVerificationMessage(verificationSent, email);
      Navigator.of(context).pushAndRemoveUntil(
        _noTransitionRoute(const HomePage()),
        (route) => false,
      );
    } catch (error) {
      if (!mounted) return;

      _isLoading.value = false;

      if (error is FirebaseAuthException) {
        _showError(_firebaseErrorMessage(error));
      } else if (error is FirebaseException) {
        _showError(
          error.plugin == 'cloud_firestore'
              ? 'Your account profile could not be saved. Please try registering again.'
              : error.message ?? 'A Firebase error occurred.',
        );
      } else {
        _showError('Something went wrong. Please try again.');
      }
    }
  }

  static String _firebaseErrorMessage(
    FirebaseAuthException error,
  ) => switch (error.code) {
    'email-already-in-use' => 'An account already exists with this email.',
    'invalid-email' => 'Enter a valid email address.',
    'weak-password' => 'Choose a stronger password.',
    'operation-not-allowed' => 'Email registration is not enabled in Firebase.',
    'network-request-failed' => 'Check your internet connection and try again.',
    'too-many-requests' => 'Too many attempts. Please try again later.',
    _ => error.message ?? 'Unable to create your account.',
  };

  void _showSnackBar(
    String message,
    Color backgroundColor,
    IconData iconData, [
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
              Icon(iconData, color: AppColors.white),
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

  void _showError(String message) {
    _showSnackBar(message, AppColors.error, Icons.error_outline_rounded);
  }

  void _showVerificationMessage(bool verificationSent, String email) {
    _showSnackBar(
      verificationSent
          ? 'Account created! Check $email to verify your email.'
          : 'Account created, but the verification email could not be sent.',
      verificationSent ? AppColors.success : AppColors.warning,
      verificationSent
          ? Icons.mark_email_read_rounded
          : Icons.warning_amber_rounded,
      const Duration(seconds: 5),
    );
  }

  static PageRouteBuilder<T> _noTransitionRoute<T>(Widget page) =>
      PageRouteBuilder<T>(
        pageBuilder: (_, _, _) => page,
        transitionDuration: Duration.zero,
        reverseTransitionDuration: Duration.zero,
      );

  void _goBack() {
    Navigator.of(context).pushAndRemoveUntil(
      _noTransitionRoute(const SplashIntroPage()),
      (route) => false,
    );
  }

  void _openLogin() {
    Navigator.of(context).push(_noTransitionRoute(const LoginPage()));
  }

  void _togglePasswordVisibility() {
    _showPassword.value = !_showPassword.value;
  }

  void _toggleConfirmPasswordVisibility() {
    _showConfirmPassword.value = !_showConfirmPassword.value;
  }

  void _submitConfirmPassword(String _) {
    _register();
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final isDark = colorScheme.brightness == Brightness.dark;
    final panel = _RegisterPanel(
      nameController: _nameController,
      emailController: _emailController,
      passwordController: _passwordController,
      confirmPasswordController: _confirmPasswordController,
      passwordVisibility: _showPassword,
      confirmPasswordVisibility: _showConfirmPassword,
      loading: _isLoading,
      onTogglePasswordVisibility: _togglePasswordVisibility,
      onToggleConfirmPasswordVisibility: _toggleConfirmPasswordVisibility,
      onConfirmPasswordSubmitted: _submitConfirmPassword,
      onRegister: _register,
      onLogin: _openLogin,
    );
    final expandedHero = _RegisterHero(compact: false, onBack: _goBack);
    final compactHero = _RegisterHero(compact: true, onBack: _goBack);

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
}

class _RegisterPanel extends StatelessWidget {
  const _RegisterPanel({
    required this.nameController,
    required this.emailController,
    required this.passwordController,
    required this.confirmPasswordController,
    required this.passwordVisibility,
    required this.confirmPasswordVisibility,
    required this.loading,
    required this.onTogglePasswordVisibility,
    required this.onToggleConfirmPasswordVisibility,
    required this.onConfirmPasswordSubmitted,
    required this.onRegister,
    required this.onLogin,
  });

  final TextEditingController nameController;
  final TextEditingController emailController;
  final TextEditingController passwordController;
  final TextEditingController confirmPasswordController;
  final ValueNotifier<bool> passwordVisibility;
  final ValueNotifier<bool> confirmPasswordVisibility;
  final ValueNotifier<bool> loading;
  final VoidCallback onTogglePasswordVisibility;
  final VoidCallback onToggleConfirmPasswordVisibility;
  final ValueChanged<String> onConfirmPasswordSubmitted;
  final VoidCallback onRegister;
  final VoidCallback onLogin;

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
                    _LoginRegisterPill(onLoginTap: onLogin),
                    const SizedBox(height: 24),
                    Text(
                      'Create your account',
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
                    _UiInputField(
                      controller: nameController,
                      hintText: 'Full name',
                      icon: Icons.person_outline_rounded,
                      keyboardType: TextInputType.name,
                      textInputAction: TextInputAction.next,
                      textCapitalization: TextCapitalization.words,
                      autofillHints: const [AutofillHints.name],
                    ),
                    const SizedBox(height: 14),
                    _UiInputField(
                      controller: emailController,
                      hintText: 'Email address',
                      icon: Icons.mail_outline_rounded,
                      keyboardType: TextInputType.emailAddress,
                      textInputAction: TextInputAction.next,
                      autofillHints: const [AutofillHints.email],
                    ),
                    const SizedBox(height: 14),
                    ValueListenableBuilder<bool>(
                      valueListenable: passwordVisibility,
                      builder: (_, isVisible, _) => _UiInputField(
                        controller: passwordController,
                        hintText: 'Password',
                        icon: Icons.lock_outline_rounded,
                        obscureText: !isVisible,
                        textInputAction: TextInputAction.next,
                        autofillHints: const [AutofillHints.newPassword],
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
                    const SizedBox(height: 14),
                    ValueListenableBuilder<bool>(
                      valueListenable: confirmPasswordVisibility,
                      builder: (_, isVisible, _) => _UiInputField(
                        controller: confirmPasswordController,
                        hintText: 'Confirm password',
                        icon: Icons.lock_reset_rounded,
                        obscureText: !isVisible,
                        textInputAction: TextInputAction.done,
                        onSubmitted: onConfirmPasswordSubmitted,
                        suffixIcon: IconButton(
                          tooltip: isVisible
                              ? 'Hide password'
                              : 'Show password',
                          onPressed: onToggleConfirmPasswordVisibility,
                          icon: Icon(
                            isVisible
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                            size: 20,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 22),
                    SizedBox(
                      width: double.infinity,
                      height: 57,
                      child: ValueListenableBuilder<bool>(
                        valueListenable: loading,
                        builder: (_, isLoading, _) => FilledButton(
                          onPressed: isLoading ? null : onRegister,
                          style: FilledButton.styleFrom(
                            backgroundColor: colorScheme.primary,
                            foregroundColor: colorScheme.onPrimary,
                            disabledBackgroundColor: colorScheme.primary
                                .withValues(alpha: 0.72),
                            disabledForegroundColor: colorScheme.onPrimary,
                            shape: const RoundedRectangleBorder(
                              borderRadius: BorderRadius.all(
                                Radius.circular(17),
                              ),
                            ),
                          ),
                          child: isLoading
                              ? SizedBox.square(
                                  dimension: 24,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2.5,
                                    color: colorScheme.onPrimary,
                                  ),
                                )
                              : const Text(
                                  'Register',
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
                        const SizedBox(width: 12),
                        Flexible(
                          flex: 2,
                          child: Text(
                            'Or register with',
                            maxLines: 2,
                            textAlign: TextAlign.center,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: colorScheme.onSurfaceVariant,
                              fontSize: 13,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(child: Divider(color: dividerColor)),
                      ],
                    ),
                    const SizedBox(height: 18),
                    const _SocialRegisterOptions(),
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

class _UiInputField extends StatelessWidget {
  const _UiInputField({
    required this.controller,
    required this.hintText,
    required this.icon,
    this.keyboardType,
    this.textInputAction,
    this.textCapitalization = TextCapitalization.none,
    this.obscureText = false,
    this.suffixIcon,
    this.onSubmitted,
    this.autofillHints,
  });

  final TextEditingController controller;
  final String hintText;
  final IconData icon;
  final TextInputType? keyboardType;
  final TextInputAction? textInputAction;
  final TextCapitalization textCapitalization;
  final bool obscureText;
  final Widget? suffixIcon;
  final ValueChanged<String>? onSubmitted;
  final Iterable<String>? autofillHints;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    const borderRadius = BorderRadius.all(Radius.circular(17));
    const enabledBorder = OutlineInputBorder(
      borderRadius: borderRadius,
      borderSide: BorderSide.none,
    );

    return TextField(
      controller: controller,
      keyboardType: keyboardType,
      textInputAction: textInputAction,
      textCapitalization: textCapitalization,
      obscureText: obscureText,
      autocorrect: false,
      enableSuggestions: !obscureText,
      autofillHints: autofillHints,
      onSubmitted: onSubmitted,
      decoration: InputDecoration(
        hintText: hintText,
        prefixIcon: Icon(
          icon,
          size: 20,
          color: colorScheme.primary.withValues(alpha: 0.88),
        ),
        suffixIcon: suffixIcon,
        filled: true,
        fillColor: colorScheme.surfaceContainerLow,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 18,
          vertical: 19,
        ),
        hintStyle: theme.textTheme.bodyMedium?.copyWith(
          color: colorScheme.onSurfaceVariant,
          fontSize: 14,
        ),
        enabledBorder: enabledBorder,
        focusedBorder: OutlineInputBorder(
          borderRadius: borderRadius,
          borderSide: BorderSide(color: colorScheme.primary, width: 1.5),
        ),
      ),
    );
  }
}

class _RegisterHero extends StatelessWidget {
  const _RegisterHero({required this.compact, required this.onBack});

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
                                  'Create Your\nAccount',
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
                                  'Create an account and start planning your next trip.',
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
      label: 'Trip Logic registration',
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
                Icons.person_add_alt_1_rounded,
                size: 18,
                color: foregroundColor,
              ),
            ),
            const SizedBox(width: 9),
            ExcludeSemantics(
              child: Text(
                'REGISTER',
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

class _LoginRegisterPill extends StatelessWidget {
  const _LoginRegisterPill({required this.onLoginTap});

  final VoidCallback onLoginTap;

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
              button: true,
              selected: false,
              child: InkWell(
                onTap: onLoginTap,
                borderRadius: const BorderRadius.all(Radius.circular(15)),
                child: Center(
                  child: Text(
                    'Login',
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
                  'Register',
                  style: theme.textTheme.titleSmall?.copyWith(
                    color: colorScheme.onPrimary,
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
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

class _SocialRegisterOptions extends StatelessWidget {
  const _SocialRegisterOptions();

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
