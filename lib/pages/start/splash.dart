import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:trip_logic/pages/start/login.dart';
import 'package:trip_logic/pages/start/terms_privacy.dart';
import 'package:trip_logic/theme/app_colors.dart';

PageRoute<T> _fadeRoute<T>(Widget page) => PageRouteBuilder<T>(
  pageBuilder: (_, _, _) => page,
  transitionDuration: Duration.zero,
  reverseTransitionDuration: Duration.zero,
);

class SplashIntroPage extends StatefulWidget {
  const SplashIntroPage({super.key, this.onExplore});

  final VoidCallback? onExplore;

  @override
  State<SplashIntroPage> createState() => _SplashIntroPageState();
}

class _SplashIntroPageState extends State<SplashIntroPage> {
  final _hasAcceptedLegal = ValueNotifier(false);

  Future<void> _openLegalPage({required String initialDocument}) async {
    final accepted = await Navigator.push<bool>(
      context,
      _fadeRoute<bool>(
        TermsPrivacyPage(
          initialDocument: initialDocument,
          onAgree: () => Navigator.pop(context, true),
          onDecline: () => Navigator.pop(context, false),
        ),
      ),
    );

    if (mounted) {
      _hasAcceptedLegal.value = accepted == true;
    }
  }

  void _showTermsRequiredDialog() {
    unawaited(
      showDialog<void>(
        context: context,
        builder: (dialogContext) {
          final theme = Theme.of(dialogContext);
          final colorScheme = theme.colorScheme;

          return AlertDialog(
            shape: const RoundedRectangleBorder(
              borderRadius: BorderRadius.all(Radius.circular(24)),
            ),
            titlePadding: const EdgeInsets.fromLTRB(24, 24, 24, 0),
            contentPadding: const EdgeInsets.fromLTRB(24, 18, 24, 8),
            actionsPadding: const EdgeInsets.fromLTRB(18, 8, 18, 18),
            title: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: colorScheme.primary.withValues(alpha: 0.11),
                    borderRadius: const BorderRadius.all(Radius.circular(14)),
                  ),
                  child: Icon(
                    Icons.gpp_good_outlined,
                    color: colorScheme.primary,
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Text(
                    'Accept Terms & Privacy first',
                    style: theme.textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w800,
                      height: 1.18,
                    ),
                  ),
                ),
              ],
            ),
            content: Text(
              'Please review and accept the Terms & Privacy information before continuing.',
              style: theme.textTheme.bodyMedium?.copyWith(height: 1.45),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogContext),
                child: const Text('Cancel'),
              ),
              FilledButton(
                onPressed: () {
                  Navigator.pop(dialogContext);
                  unawaited(_openLegalPage(initialDocument: 'terms'));
                },
                child: const Text('Review now'),
              ),
            ],
          );
        },
      ),
    );
  }

  void _handleExplore() {
    if (!_hasAcceptedLegal.value) {
      _showTermsRequiredDialog();
      return;
    }

    widget.onExplore?.call();

    if (!mounted) {
      return;
    }

    unawaited(
      Navigator.push<void>(context, _fadeRoute<void>(const LoginPage())),
    );
  }

  @override
  void dispose() {
    _hasAcceptedLegal.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle(
        statusBarColor: AppColors.transparent,
        statusBarBrightness: Brightness.dark,
        statusBarIconBrightness: Brightness.light,
        systemNavigationBarColor: colorScheme.surface,
        systemNavigationBarIconBrightness:
            colorScheme.brightness == Brightness.dark
            ? Brightness.light
            : Brightness.dark,
        systemNavigationBarDividerColor: AppColors.transparent,
        systemStatusBarContrastEnforced: false,
        systemNavigationBarContrastEnforced: false,
      ),
      child: Scaffold(
        backgroundColor: colorScheme.surface,
        body: LayoutBuilder(
          builder: (_, constraints) {
            final screenHeight = constraints.maxHeight;
            final heroHeight = screenHeight * 0.65;
            final panelTop = (heroHeight - 34).clamp(0.0, screenHeight);

            return Stack(
              children: [
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  height: heroHeight,
                  child: const _SplashHero(),
                ),
                Positioned(
                  top: panelTop,
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: _SplashContentPanel(
                    acceptedLegal: _hasAcceptedLegal,
                    onExplore: _handleExplore,
                    onOpenTerms: () => _openLegalPage(initialDocument: 'terms'),
                    onOpenPrivacy: () =>
                        _openLegalPage(initialDocument: 'privacy'),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _SplashHero extends StatelessWidget {
  const _SplashHero();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Stack(
      fit: StackFit.expand,
      children: [
        Image.asset(
          'lib/assets/images/startup/splash_screen_bg.webp',
          fit: BoxFit.cover,
          alignment: const Alignment(0, 0.18),
          filterQuality: FilterQuality.high,
          excludeFromSemantics: true,
        ),
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              stops: const [0, 0.44, 1],
              colors: [
                AppColors.black.withValues(alpha: 0.42),
                AppColors.transparent,
                AppColors.black.withValues(alpha: 0.82),
              ],
            ),
          ),
        ),
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.bottomLeft,
              end: Alignment.topRight,
              colors: [
                AppColors.primaryVariant.withValues(alpha: 0.34),
                AppColors.transparent,
                AppColors.transparent,
              ],
            ),
          ),
        ),
        SafeArea(
          bottom: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(22, 14, 22, 62),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _BrandBadge(),
                const Spacer(),
                Text(
                  'Trips built\naround you.',
                  maxLines: 2,
                  style: theme.textTheme.headlineLarge?.copyWith(
                    color: AppColors.white,
                    fontSize: 38,
                    fontWeight: FontWeight.w800,
                    height: 1.02,
                    letterSpacing: -1,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _BrandBadge extends StatelessWidget {
  const _BrandBadge();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    final isDark = theme.brightness == Brightness.dark;
    final containerColor = isDark
        ? AppColors.black.withValues(alpha: 0.30)
        : AppColors.white.withValues(alpha: 0.72);
    final containerBorderColor = isDark
        ? AppColors.white.withValues(alpha: 0.24)
        : theme.colorScheme.onSurface.withValues(alpha: 0.12);
    final textColor = isDark ? AppColors.white : theme.colorScheme.onSurface;

    return Semantics(
      label: 'Trip Logic',
      child: Container(
        height: 44,
        padding: const EdgeInsets.fromLTRB(5, 5, 16, 5),
        decoration: BoxDecoration(
          color: containerColor,
          borderRadius: const BorderRadius.all(Radius.circular(24)),
          border: Border.all(color: containerBorderColor),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 34,
              height: 34,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.primary,
              ),
              child: Image.asset(
                'lib/assets/images/startup/app_icon.png',
                fit: BoxFit.contain,
              ),
            ),
            const SizedBox(width: 10),
            ExcludeSemantics(
              child: Text(
                'Trip Logic',
                style: theme.textTheme.labelLarge?.copyWith(
                  color: textColor,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.1,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SplashContentPanel extends StatelessWidget {
  const _SplashContentPanel({
    required this.acceptedLegal,
    required this.onExplore,
    required this.onOpenTerms,
    required this.onOpenPrivacy,
  });

  final ValueNotifier<bool> acceptedLegal;
  final VoidCallback onExplore;
  final VoidCallback onOpenTerms;
  final VoidCallback onOpenPrivacy;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final isDark = colorScheme.brightness == Brightness.dark;
    final bottomInset = MediaQuery.viewPaddingOf(context).bottom;

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
        child: SingleChildScrollView(
          padding: EdgeInsets.fromLTRB(24, 30, 24, bottomInset + 18),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 7,
                    ),
                    decoration: BoxDecoration(
                      color: colorScheme.primary.withValues(alpha: 0.10),
                      borderRadius: const BorderRadius.all(
                        Radius.circular(999),
                      ),
                      border: Border.all(
                        color: colorScheme.primary.withValues(alpha: 0.16),
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.near_me_rounded,
                          size: 15,
                          color: colorScheme.primary,
                        ),
                        const SizedBox(width: 7),
                        Text(
                          'PERSONALIZED TRAVEL',
                          style: theme.textTheme.labelSmall?.copyWith(
                            color: colorScheme.primary,
                            fontWeight: FontWeight.w800,
                            letterSpacing: 0.75,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Explore more. Plan less.',
                    style: theme.textTheme.headlineMedium?.copyWith(
                      color: colorScheme.onSurface,
                      fontSize: 29,
                      fontWeight: FontWeight.w800,
                      height: 1.08,
                      letterSpacing: -0.65,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'Personalized places, routes and plans, made for the way you travel.',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: colorScheme.onSurfaceVariant,
                      fontSize: 14,
                      height: 1.45,
                    ),
                  ),
                  const SizedBox(height: 50),
                  ValueListenableBuilder<bool>(
                    valueListenable: acceptedLegal,
                    builder: (_, hasAcceptedLegal, _) => Column(
                      children: [
                        _SlideToExplore(
                          onCompleted: onExplore,
                          resetSignal: hasAcceptedLegal,
                        ),
                        const SizedBox(height: 12),
                        _LegalNotice(
                          hasAcceptedLegal: hasAcceptedLegal,
                          onOpenTerms: onOpenTerms,
                          onOpenPrivacy: onOpenPrivacy,
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
    );
  }
}

class _LegalNotice extends StatelessWidget {
  const _LegalNotice({
    required this.hasAcceptedLegal,
    required this.onOpenTerms,
    required this.onOpenPrivacy,
  });

  final bool hasAcceptedLegal;
  final VoidCallback onOpenTerms;
  final VoidCallback onOpenPrivacy;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    final linkStyle = theme.textTheme.bodySmall?.copyWith(
      color: colorScheme.primary,
      decoration: TextDecoration.underline,
      decorationColor: colorScheme.primary,
      fontWeight: FontWeight.w700,
      height: 1.45,
    );

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 1),
          child: Icon(
            hasAcceptedLegal ? Icons.verified_rounded : Icons.shield_outlined,
            size: 18,
            color: colorScheme.primary,
          ),
        ),
        const SizedBox(width: 9),
        Expanded(
          child: Text.rich(
            TextSpan(
              style: theme.textTheme.bodySmall?.copyWith(
                color: colorScheme.onSurfaceVariant,
                fontSize: 12,
                height: 1.45,
              ),
              children: [
                TextSpan(
                  text: hasAcceptedLegal
                      ? 'Accepted. You can review the '
                      : 'Please read the ',
                ),
                WidgetSpan(
                  alignment: PlaceholderAlignment.middle,
                  child: GestureDetector(
                    onTap: onOpenTerms,
                    child: Text('Terms & Conditions', style: linkStyle),
                  ),
                ),
                const TextSpan(text: ' and '),
                WidgetSpan(
                  alignment: PlaceholderAlignment.middle,
                  child: GestureDetector(
                    onTap: onOpenPrivacy,
                    child: Text('Privacy Policy', style: linkStyle),
                  ),
                ),
                TextSpan(
                  text: hasAcceptedLegal
                      ? ' at any time.'
                      : ' before continuing.',
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _SlideToExplore extends StatefulWidget {
  const _SlideToExplore({required this.onCompleted, this.resetSignal = false});

  final VoidCallback onCompleted;
  final bool resetSignal;

  @override
  State<_SlideToExplore> createState() => _SlideToExploreState();
}

class _SlideToExploreState extends State<_SlideToExplore> {
  static const _height = 62.0;
  static const _thumbSize = 52.0;
  static const _padding = 5.0;
  static const _borderRadius = BorderRadius.all(Radius.circular(31));

  double _dragPosition = 0;
  bool _isDragging = false;
  bool _isCompleted = false;

  @override
  void didUpdateWidget(covariant _SlideToExplore oldWidget) {
    super.didUpdateWidget(oldWidget);

    if (widget.resetSignal && !oldWidget.resetSignal) {
      _dragPosition = 0;
      _isDragging = false;
      _isCompleted = false;
    }
  }

  void _startDragging(DragStartDetails _) {
    if (_isCompleted) {
      return;
    }

    setState(() => _isDragging = true);
    unawaited(HapticFeedback.selectionClick());
  }

  void _updateDragging(DragUpdateDetails details, double maxDrag) {
    if (_isCompleted) {
      return;
    }

    final dragPosition = (_dragPosition + details.delta.dx)
        .clamp(0.0, maxDrag)
        .toDouble();

    if (dragPosition != _dragPosition) {
      setState(() => _dragPosition = dragPosition);
    }
  }

  void _finishDragging(double maxDrag) {
    if (_isCompleted) {
      return;
    }

    final completed = _dragPosition >= maxDrag * 0.72;
    final shouldStayCompleted = completed && widget.resetSignal;

    setState(() {
      _isDragging = false;
      _dragPosition = shouldStayCompleted ? maxDrag : 0;
      _isCompleted = shouldStayCompleted;
    });

    if (!completed) {
      unawaited(HapticFeedback.selectionClick());
      return;
    }

    unawaited(HapticFeedback.mediumImpact());
    unawaited(
      Future<void>.delayed(const Duration(milliseconds: 280), () {
        if (mounted) {
          widget.onCompleted();
        }
      }),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final primary = colorScheme.primary;
    final trackStartColor = primary.withValues(alpha: 0.16);
    final label = Transform.translate(
      offset: const Offset(9, 0),
      child: Text(
        'Slide to explore',
        style: theme.textTheme.bodyMedium?.copyWith(
          fontSize: 16,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.15,
          color: colorScheme.onSurface,
        ),
      ),
    );

    return Semantics(
      label: 'Slide to explore',
      hint: 'Drag the circular handle to the right',
      value: _isCompleted ? 'Completed' : 'Not completed',
      child: LayoutBuilder(
        builder: (_, constraints) {
          final maxDrag = (constraints.maxWidth - _thumbSize - (_padding * 2))
              .clamp(0.0, double.infinity)
              .toDouble();

          return RepaintBoundary(
            child: Container(
              height: _height,
              decoration: BoxDecoration(
                borderRadius: _borderRadius,
                boxShadow: [
                  BoxShadow(
                    color: colorScheme.shadow.withValues(alpha: 0.10),
                    blurRadius: 20,
                    spreadRadius: -8,
                    offset: const Offset(0, 10),
                  ),
                ],
              ),
              child: ClipRRect(
                borderRadius: _borderRadius,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: colorScheme.surfaceContainerLow,
                    borderRadius: _borderRadius,
                    border: Border.all(
                      color: colorScheme.outlineVariant.withValues(alpha: 0.62),
                    ),
                  ),
                  child: TweenAnimationBuilder<double>(
                    tween: Tween<double>(end: _dragPosition),
                    duration: _isDragging
                        ? Duration.zero
                        : const Duration(milliseconds: 300),
                    curve: Curves.easeOutCubic,
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onHorizontalDragStart: _startDragging,
                      onHorizontalDragUpdate: (details) =>
                          _updateDragging(details, maxDrag),
                      onHorizontalDragEnd: (_) => _finishDragging(maxDrag),
                      onHorizontalDragCancel: () => _finishDragging(maxDrag),
                      child: Container(
                        width: _thumbSize,
                        height: _thumbSize,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: primary,
                          border: Border.all(
                            color: colorScheme.onPrimary.withValues(
                              alpha: 0.22,
                            ),
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: primary.withValues(alpha: 0.20),
                              blurRadius: 16,
                              offset: const Offset(0, 7),
                            ),
                          ],
                        ),
                        child: Icon(
                          _isCompleted
                              ? Icons.check_rounded
                              : Icons.arrow_forward_rounded,
                          size: 23,
                          color: colorScheme.onPrimary,
                        ),
                      ),
                    ),
                    builder: (_, animatedDrag, thumb) {
                      final progress = maxDrag == 0
                          ? 0.0
                          : (animatedDrag / maxDrag).clamp(0.0, 1.0).toDouble();
                      final thumbCenter =
                          _padding + animatedDrag + (_thumbSize / 2);
                      final textOpacity = progress <= 0.16
                          ? 1.0
                          : (1 - ((progress - 0.16) / 0.14))
                                .clamp(0.0, 1.0)
                                .toDouble();

                      return Stack(
                        alignment: Alignment.centerLeft,
                        children: [
                          Positioned(
                            left: 0,
                            top: 0,
                            bottom: 0,
                            width: _thumbSize + (_padding * 2) + animatedDrag,
                            child: DecoratedBox(
                              decoration: BoxDecoration(
                                borderRadius: _borderRadius,
                                gradient: LinearGradient(
                                  colors: [
                                    trackStartColor,
                                    primary.withValues(
                                      alpha: 0.08 + progress * 0.10,
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                          Positioned.fill(
                            child: IgnorePointer(
                              child: RepaintBoundary(
                                child: CustomPaint(
                                  painter: _TravelIconsPainter(
                                    thumbCenter: thumbCenter,
                                    color: primary,
                                  ),
                                ),
                              ),
                            ),
                          ),
                          Positioned.fill(
                            child: IgnorePointer(
                              child: Center(
                                child: Opacity(
                                  opacity: _isCompleted ? 0 : textOpacity,
                                  child: label,
                                ),
                              ),
                            ),
                          ),
                          Positioned(
                            left: _padding + animatedDrag,
                            top: _padding,
                            child: thumb!,
                          ),
                        ],
                      );
                    },
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _TravelIconsPainter extends CustomPainter {
  const _TravelIconsPainter({required this.thumbCenter, required this.color});

  final double thumbCenter;
  final Color color;

  static const _icons = <IconData>[
    Icons.location_on_rounded,
    Icons.travel_explore_rounded,
    Icons.hotel_rounded,
    Icons.restaurant_rounded,
    Icons.route_rounded,
    Icons.map_rounded,
  ];

  @override
  void paint(Canvas canvas, Size size) {
    final startX = size.width * 0.15;
    final endX = size.width * 0.75;
    final spacing = (endX - startX) / (_icons.length - 1);
    final centerY = size.height / 2;
    TextPainter? painter;

    for (var index = 0; index < _icons.length; index++) {
      final x = startX + spacing * index;
      final reveal = ((thumbCenter - x - 26) / 34).clamp(0.0, 1.0).toDouble();

      if (reveal <= 0) {
        continue;
      }

      final easedReveal = Curves.easeOutCubic.transform(reveal);
      final scale = 0.38 + easedReveal * 0.58;
      final rise = (1 - easedReveal) * 10;
      final drift = (1 - reveal) * 6;
      final opacity = (0.12 + easedReveal * 0.88).clamp(0.0, 1.0).toDouble();
      final icon = _icons[index];
      final iconPainter = painter ??= TextPainter(
        textDirection: TextDirection.ltr,
      );
      iconPainter
        ..text = TextSpan(
          text: String.fromCharCode(icon.codePoint),
          style: TextStyle(
            fontFamily: icon.fontFamily,
            package: icon.fontPackage,
            fontSize: 17,
            color: color.withValues(alpha: opacity * 0.92),
          ),
        )
        ..layout();

      canvas
        ..save()
        ..translate(x + drift, centerY + rise)
        ..scale(scale);
      iconPainter.paint(
        canvas,
        Offset(-iconPainter.width / 2, -iconPainter.height / 2),
      );
      canvas.restore();
    }

    painter?.dispose();
  }

  @override
  bool shouldRepaint(covariant _TravelIconsPainter oldDelegate) =>
      oldDelegate.thumbCenter != thumbCenter || oldDelegate.color != color;
}
