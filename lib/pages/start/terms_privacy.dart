import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:trip_logic/theme/app_colors.dart';

enum _LegalDocument { terms, privacy }

class TermsPrivacyPage extends StatefulWidget {
  const TermsPrivacyPage({
    super.key,
    this.onAgree,
    this.onDecline,
    this.initialDocument,
  });

  final VoidCallback? onAgree;
  final VoidCallback? onDecline;
  final String? initialDocument;

  @override
  State<TermsPrivacyPage> createState() => _TermsPrivacyPageState();
}

class _TermsPrivacyPageState extends State<TermsPrivacyPage> {
  final _documentTopKey = GlobalKey();

  late final ValueNotifier<_LegalDocument> _selectedDocument;
  final _hasAccepted = ValueNotifier(false);

  @override
  void initState() {
    super.initState();
    _selectedDocument = ValueNotifier(
      widget.initialDocument == 'privacy'
          ? _LegalDocument.privacy
          : _LegalDocument.terms,
    );
  }

  void _goBack() {
    FocusManager.instance.primaryFocus?.unfocus();
    Navigator.maybePop(context);
  }

  void _selectDocument(_LegalDocument document) {
    if (_selectedDocument.value == document) {
      return;
    }

    _selectedDocument.value = document;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      final targetContext = _documentTopKey.currentContext;

      if (targetContext == null) {
        return;
      }

      Scrollable.ensureVisible(
        targetContext,
        duration: const Duration(milliseconds: 420),
        curve: Curves.easeInOutCubic,
      );
    });
  }

  void _agreeAndContinue() {
    if (!_hasAccepted.value) {
      return;
    }

    if (widget.onAgree != null) {
      widget.onAgree!();
      return;
    }

    Navigator.maybePop(context, true);
  }

  void _decline() {
    if (widget.onDecline != null) {
      widget.onDecline!();
      return;
    }

    Navigator.maybePop(context, false);
  }

  @override
  void dispose() {
    _selectedDocument.dispose();
    _hasAccepted.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final isDark = colorScheme.brightness == Brightness.dark;

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
      child: Scaffold(
        resizeToAvoidBottomInset: false,
        backgroundColor: colorScheme.surface,
        body: LayoutBuilder(
          builder: (_, constraints) {
            final screenHeight = constraints.maxHeight;
            final heroHeight = (screenHeight * 0.40)
                .clamp(226.0, 280.0)
                .toDouble();
            final panelTop = (heroHeight - 34).clamp(0.0, screenHeight);

            return Stack(
              children: [
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  height: heroHeight,
                  child: _LegalHero(onBack: _goBack),
                ),
                Positioned.fill(
                  top: panelTop,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: colorScheme.surface,
                      borderRadius: const BorderRadius.vertical(
                        top: Radius.circular(34),
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: colorScheme.shadow.withValues(
                            alpha: isDark ? 0.30 : 0.14,
                          ),
                          blurRadius: 34,
                          spreadRadius: -10,
                          offset: const Offset(0, -8),
                        ),
                      ],
                    ),
                    child: ClipRRect(
                      borderRadius: const BorderRadius.vertical(
                        top: Radius.circular(34),
                      ),
                      child: SingleChildScrollView(
                        padding: const EdgeInsets.fromLTRB(24, 30, 24, 30),
                        child: Center(
                          child: ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 720),
                            child: Column(
                              key: _documentTopKey,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const _SectionLabel(),
                                const SizedBox(height: 16),
                                Text(
                                  'Before you continue',
                                  style: theme.textTheme.titleLarge?.copyWith(
                                    color: colorScheme.onSurface,
                                    fontSize: 24,
                                    fontWeight: FontWeight.w800,
                                    letterSpacing: -0.45,
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  'Trip Logic uses location and travel preferences to provide recommendations, routes and itineraries.',
                                  style: theme.textTheme.bodyMedium?.copyWith(
                                    color: colorScheme.onSurfaceVariant,
                                    fontSize: 14,
                                    height: 1.5,
                                  ),
                                ),
                                const SizedBox(height: 22),
                                const _LegalNotice(),
                                const SizedBox(height: 24),
                                ValueListenableBuilder<_LegalDocument>(
                                  valueListenable: _selectedDocument,
                                  builder: (_, selectedDocument, _) => Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      _DocumentPill(
                                        selectedDocument: selectedDocument,
                                        onTermsPressed: () => _selectDocument(
                                          _LegalDocument.terms,
                                        ),
                                        onPrivacyPressed: () => _selectDocument(
                                          _LegalDocument.privacy,
                                        ),
                                      ),
                                      const SizedBox(height: 24),
                                      selectedDocument == _LegalDocument.terms
                                          ? const _LegalDocumentView(
                                              key: ValueKey('terms'),
                                              title: 'Terms and Conditions',
                                              subtitle:
                                                  'Responsible and lawful use of Trip Logic.',
                                              sections: _termsSections,
                                              contactDescription:
                                                  'For questions about these Terms and Conditions, contact:',
                                            )
                                          : const _LegalDocumentView(
                                              key: ValueKey('privacy'),
                                              title: 'Privacy Policy',
                                              subtitle:
                                                  'How Trip Logic handles your information.',
                                              sections: _privacySections,
                                              contactDescription:
                                                  'For questions about the Privacy Policy, contact:',
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
                  ),
                ),
              ],
            );
          },
        ),
        bottomNavigationBar: ValueListenableBuilder<bool>(
          valueListenable: _hasAccepted,
          builder: (_, value, _) => _AgreementArea(
            value: value,
            onChanged: (value) => _hasAccepted.value = value,
            onAgree: _agreeAndContinue,
            onDecline: _decline,
          ),
        ),
      ),
    );
  }
}

class _LegalHero extends StatelessWidget {
  const _LegalHero({required this.onBack});

  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Stack(
      fit: StackFit.expand,
      children: [
        Image.asset(
          'lib/assets/images/startup/bg.webp',
          fit: BoxFit.cover,
          alignment: Alignment.topCenter,
          filterQuality: FilterQuality.high,
          excludeFromSemantics: true,
        ),
        DecoratedBox(
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
        ),
        SafeArea(
          bottom: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(22, 14, 22, 54),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    _BackButton(onPressed: onBack),
                    const Spacer(),
                    const _LegalBrandBadge(),
                  ],
                ),
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
                                'Legal & Privacy',
                                style: theme.textTheme.headlineLarge?.copyWith(
                                  color: AppColors.white,
                                  fontSize: 32,
                                  height: 1.08,
                                  fontWeight: FontWeight.w800,
                                  letterSpacing: -0.7,
                                ),
                              ),
                              const SizedBox(height: 7),
                              Text(
                                'Please review these documents before continuing.',
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
            ),
          ),
        ),
      ],
    );
  }
}

class _LegalBrandBadge extends StatelessWidget {
  const _LegalBrandBadge();

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
      label: 'Trip Logic legal documents',
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
                Icons.policy_outlined,
                size: 18,
                color: foregroundColor,
              ),
            ),
            const SizedBox(width: 9),
            ExcludeSemantics(
              child: Text(
                'LEGAL',
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

    return Material(
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
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      decoration: BoxDecoration(
        color: colorScheme.primary.withValues(alpha: 0.10),
        borderRadius: const BorderRadius.all(Radius.circular(999)),
        border: Border.all(color: colorScheme.primary.withValues(alpha: 0.16)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.verified_user_outlined,
            size: 15,
            color: colorScheme.primary,
          ),
          const SizedBox(width: 7),
          Flexible(
            child: Text(
              'YOUR TRIP, YOUR CHOICE',
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.labelSmall?.copyWith(
                color: colorScheme.primary,
                fontWeight: FontWeight.w800,
                letterSpacing: 0.75,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _LegalNotice extends StatelessWidget {
  const _LegalNotice();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final noticeStyle = theme.textTheme.bodySmall?.copyWith(
      color: colorScheme.onSurfaceVariant,
      fontSize: 12.5,
      height: 1.5,
    );

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: colorScheme.primary.withValues(alpha: 0.065),
        borderRadius: const BorderRadius.all(Radius.circular(22)),
        border: Border.all(color: colorScheme.primary.withValues(alpha: 0.15)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: colorScheme.primary.withValues(alpha: 0.13),
              borderRadius: const BorderRadius.all(Radius.circular(13)),
            ),
            child: Icon(
              Icons.info_outline_rounded,
              color: colorScheme.primary,
              size: 21,
            ),
          ),

          const SizedBox(width: 13),

          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Important notice',
                  style: theme.textTheme.titleSmall?.copyWith(
                    color: colorScheme.onSurface,
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                  ),
                ),

                const SizedBox(height: 5),

                Text(
                  'This version assumes Trip Logic has no payments, bookings, user accounts or permanent location history.',
                  style: noticeStyle,
                ),

                const SizedBox(height: 6),

                Text(
                  'Sri Lanka’s Personal Data Protection Act, No. 9 of 2022 regulates personal-data processing and was amended by Act No. 22 of 2025.',
                  style: noticeStyle,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _DocumentPill extends StatelessWidget {
  const _DocumentPill({
    required this.selectedDocument,
    required this.onTermsPressed,
    required this.onPrivacyPressed,
  });

  final _LegalDocument selectedDocument;
  final VoidCallback onTermsPressed;
  final VoidCallback onPrivacyPressed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final termsSelected = selectedDocument == _LegalDocument.terms;

    final activeTabTextColor = colorScheme.onPrimary;
    final inactiveTabTextColor = colorScheme.onSurfaceVariant;
    final activeTabStyle = theme.textTheme.titleSmall?.copyWith(
      color: activeTabTextColor,
      fontSize: 13,
      height: 1.15,
      fontWeight: FontWeight.w700,
    );
    final inactiveTabStyle = theme.textTheme.titleSmall?.copyWith(
      color: inactiveTabTextColor,
      fontSize: 13,
      height: 1.15,
      fontWeight: FontWeight.w600,
    );

    return Container(
      height: 60,
      padding: const EdgeInsets.all(5),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerLow,
        borderRadius: const BorderRadius.all(Radius.circular(20)),
        border: Border.all(
          color: colorScheme.outlineVariant.withValues(alpha: 0.58),
        ),
      ),
      child: LayoutBuilder(
        builder: (_, constraints) {
          final tabWidth = constraints.maxWidth / 2;

          return Stack(
            children: [
              Align(
                alignment: termsSelected
                    ? Alignment.centerLeft
                    : Alignment.centerRight,
                child: Container(
                  width: tabWidth,
                  height: double.infinity,
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
                ),
              ),

              Row(
                children: [
                  Expanded(
                    child: Semantics(
                      button: true,
                      selected: termsSelected,
                      child: InkWell(
                        onTap: onTermsPressed,
                        borderRadius: const BorderRadius.all(
                          Radius.circular(15),
                        ),
                        child: SizedBox(
                          height: double.infinity,
                          child: Center(
                            child: Padding(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 8,
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(
                                    Icons.description_outlined,
                                    size: 17,
                                    color: termsSelected
                                        ? activeTabTextColor
                                        : inactiveTabTextColor,
                                  ),
                                  const SizedBox(width: 7),
                                  Flexible(
                                    child: Text(
                                      'Terms & Conditions',
                                      maxLines: 2,
                                      textAlign: TextAlign.center,
                                      style: termsSelected
                                          ? activeTabStyle
                                          : inactiveTabStyle,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),

                  Expanded(
                    child: Semantics(
                      button: true,
                      selected: !termsSelected,
                      child: InkWell(
                        onTap: onPrivacyPressed,
                        borderRadius: const BorderRadius.all(
                          Radius.circular(15),
                        ),
                        child: SizedBox(
                          height: double.infinity,
                          child: Center(
                            child: Padding(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 8,
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(
                                    Icons.shield_outlined,
                                    size: 17,
                                    color: !termsSelected
                                        ? activeTabTextColor
                                        : inactiveTabTextColor,
                                  ),
                                  const SizedBox(width: 7),
                                  Flexible(
                                    child: Text(
                                      'Privacy Policy',
                                      maxLines: 2,
                                      textAlign: TextAlign.center,
                                      style: termsSelected
                                          ? inactiveTabStyle
                                          : activeTabStyle,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          );
        },
      ),
    );
  }
}

class _LegalDocumentView extends StatelessWidget {
  const _LegalDocumentView({
    super.key,
    required this.title,
    required this.subtitle,
    required this.sections,
    required this.contactDescription,
  });

  final String title;
  final String subtitle;
  final List<_LegalSectionData> sections;
  final String contactDescription;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final dividerColor = colorScheme.outlineVariant.withValues(alpha: 0.20);
    final expansionTheme = theme.copyWith(
      highlightColor: AppColors.transparent,
      hoverColor: AppColors.transparent,
      splashFactory: NoSplash.splashFactory,
      expansionTileTheme: const ExpansionTileThemeData(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(20)),
        ),
        collapsedShape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(20)),
        ),
      ),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            color: colorScheme.primary.withValues(alpha: 0.065),
            borderRadius: const BorderRadius.all(Radius.circular(22)),
            border: Border.all(
              color: colorScheme.primary.withValues(alpha: 0.14),
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: colorScheme.primary.withValues(alpha: 0.13),
                  borderRadius: const BorderRadius.all(Radius.circular(14)),
                ),
                child: Icon(
                  title == 'Privacy Policy'
                      ? Icons.shield_outlined
                      : Icons.description_outlined,
                  size: 22,
                  color: colorScheme.primary,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: theme.textTheme.titleLarge?.copyWith(
                        color: colorScheme.onSurface,
                        fontSize: 21,
                        height: 1.22,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.3,
                      ),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      subtitle,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: colorScheme.onSurfaceVariant,
                        fontSize: 13.5,
                        height: 1.45,
                      ),
                    ),
                    const SizedBox(height: 11),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 5,
                      ),
                      decoration: BoxDecoration(
                        color: colorScheme.surface.withValues(alpha: 0.72),
                        borderRadius: const BorderRadius.all(
                          Radius.circular(999),
                        ),
                      ),
                      child: Text(
                        'Last updated: 13 July 2026',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: colorScheme.onSurfaceVariant,
                          fontSize: 11.5,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 20),

        SelectableText(
          sections.first.paragraphs.first,
          style: theme.textTheme.bodyMedium?.copyWith(
            color: colorScheme.onSurfaceVariant,
            fontSize: 13.5,
            height: 1.6,
          ),
        ),

        const SizedBox(height: 20),

        DecoratedBox(
          decoration: BoxDecoration(
            color: colorScheme.surfaceContainerLow,
            borderRadius: const BorderRadius.all(Radius.circular(22)),
          ),
          child: ClipRRect(
            borderRadius: const BorderRadius.all(Radius.circular(22)),
            child: Theme(
              data: expansionTheme,
              child: Column(
                children: [
                  for (var index = 0; index < sections.length; index++) ...[
                    _LegalExpansionTile(
                      section: sections[index],
                      initiallyExpanded: index == 0,
                    ),
                    if (index != sections.length - 1)
                      Divider(height: 1, thickness: 1, color: dividerColor),
                  ],
                ],
              ),
            ),
          ),
        ),

        const SizedBox(height: 22),

        _ContactSection(description: contactDescription),
      ],
    );
  }
}

class _LegalExpansionTile extends StatelessWidget {
  const _LegalExpansionTile({
    required this.section,
    required this.initiallyExpanded,
  });

  final _LegalSectionData section;
  final bool initiallyExpanded;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerLow,
        borderRadius: const BorderRadius.all(Radius.circular(20)),
      ),
      child: ClipRRect(
        borderRadius: const BorderRadius.all(Radius.circular(20)),
        child: ExpansionTile(
          key: PageStorageKey<String>('${section.number}-${section.title}'),
          initiallyExpanded: initiallyExpanded,
          maintainState: true,
          tilePadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          childrenPadding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
          iconColor: colorScheme.primary,
          collapsedIconColor: colorScheme.onSurfaceVariant,
          leading: Container(
            width: 36,
            height: 36,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: colorScheme.primary.withValues(alpha: 0.11),
              borderRadius: const BorderRadius.all(Radius.circular(12)),
            ),
            child: Text(
              section.number,
              style: theme.textTheme.titleMedium?.copyWith(
                color: colorScheme.primary,
                fontSize: 13,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
          title: Text(
            section.title,
            style: theme.textTheme.titleSmall?.copyWith(
              color: colorScheme.onSurface,
              fontSize: 14.5,
              height: 1.35,
              fontWeight: FontWeight.w700,
            ),
          ),
          children: [_SectionContent(section: section)],
        ),
      ),
    );
  }
}

class _SectionContent extends StatelessWidget {
  const _SectionContent({required this.section});

  final _LegalSectionData section;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final paragraphStyle = theme.textTheme.bodyMedium?.copyWith(
      color: theme.colorScheme.onSurfaceVariant,
      fontSize: 13.25,
      height: 1.58,
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var index = 0; index < section.paragraphs.length; index++) ...[
          // SelectableText owns a Scrollable, so it needs a nested storage
          // identity separate from the ExpansionTile's boolean state.
          SelectableText(
            section.paragraphs[index],
            key: PageStorageKey<String>(
              'legal-paragraph-${section.number}-${section.title}-$index',
            ),
            style: paragraphStyle,
          ),
          if (index != section.paragraphs.length - 1)
            const SizedBox(height: 10),
        ],
      ],
    );
  }
}

class _ContactSection extends StatelessWidget {
  const _ContactSection({required this.description});

  final String description;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerLow,
        borderRadius: const BorderRadius.all(Radius.circular(22)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  color: colorScheme.primary.withValues(alpha: 0.11),
                  borderRadius: const BorderRadius.all(Radius.circular(12)),
                ),
                child: Icon(
                  Icons.support_agent_rounded,
                  size: 20,
                  color: colorScheme.primary,
                ),
              ),

              const SizedBox(width: 12),

              Text(
                'Contact',
                style: theme.textTheme.titleSmall?.copyWith(
                  color: colorScheme.onSurface,
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),

          const SizedBox(height: 13),

          Text(
            description,
            style: theme.textTheme.bodySmall?.copyWith(
              color: colorScheme.onSurfaceVariant,
              fontSize: 13,
              height: 1.5,
            ),
          ),

          const SizedBox(height: 15),

          const _ContactRow(
            icon: Icons.person_outline_rounded,
            label: 'Support',
            value: 'Trip Logic Support',
          ),

          const SizedBox(height: 12),

          const _ContactRow(
            icon: Icons.mail_outline_rounded,
            label: 'Email',
            value: 'support@triplogic.app',
          ),
        ],
      ),
    );
  }
}

class _ContactRow extends StatelessWidget {
  const _ContactRow({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 19, color: colorScheme.primary),

        const SizedBox(width: 11),

        SizedBox(
          width: 76,
          child: Text(
            label,
            style: theme.textTheme.bodySmall?.copyWith(
              color: colorScheme.onSurfaceVariant,
              fontSize: 12.5,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),

        Expanded(
          child: SelectableText(
            value,
            style: theme.textTheme.bodySmall?.copyWith(
              color: colorScheme.onSurface,
              fontSize: 12.5,
              height: 1.45,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      ],
    );
  }
}

class _AgreementArea extends StatelessWidget {
  const _AgreementArea({
    required this.value,
    required this.onChanged,
    required this.onAgree,
    required this.onDecline,
  });

  final bool value;
  final ValueChanged<bool> onChanged;
  final VoidCallback onAgree;
  final VoidCallback onDecline;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final textScale = MediaQuery.textScalerOf(context).scale(1);
    final emphasisStyle = TextStyle(
      color: colorScheme.onSurface,
      fontWeight: FontWeight.w700,
    );
    final declineButton = OutlinedButton(
      onPressed: onDecline,
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(52),
        foregroundColor: colorScheme.onSurfaceVariant,
        side: BorderSide(
          color: colorScheme.outlineVariant.withValues(alpha: 0.82),
        ),
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(16)),
        ),
      ),
      child: const Text(
        'Decline',
        style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
      ),
    );
    final agreeButton = FilledButton(
      onPressed: value ? onAgree : null,
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(52),
        backgroundColor: colorScheme.primary,
        foregroundColor: colorScheme.onPrimary,
        disabledBackgroundColor: colorScheme.surfaceContainerHighest,
        disabledForegroundColor: colorScheme.onSurfaceVariant.withValues(
          alpha: 0.50,
        ),
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(16)),
        ),
      ),
      child: const Text(
        'Agree and Continue',
        textAlign: TextAlign.center,
        style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
      ),
    );

    return Material(
      color: colorScheme.surface,
      elevation: 14,
      shadowColor: colorScheme.shadow.withValues(alpha: 0.18),
      child: SafeArea(
        top: false,
        child: Center(
          heightFactor: 1,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 720),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(18, 13, 18, 14),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  MergeSemantics(
                    child: InkWell(
                      onTap: () => onChanged(!value),
                      borderRadius: const BorderRadius.all(Radius.circular(18)),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            SizedBox.square(
                              dimension: 24,
                              child: Checkbox(
                                value: value,
                                activeColor: colorScheme.primary,
                                checkColor: colorScheme.onPrimary,
                                materialTapTargetSize:
                                    MaterialTapTargetSize.shrinkWrap,
                                shape: const RoundedRectangleBorder(
                                  borderRadius: BorderRadius.all(
                                    Radius.circular(6),
                                  ),
                                ),
                                onChanged: (newValue) =>
                                    onChanged(newValue ?? false),
                              ),
                            ),
                            const SizedBox(width: 11),
                            Expanded(
                              child: Text.rich(
                                TextSpan(
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: colorScheme.onSurfaceVariant,
                                    fontSize: 12.25,
                                    height: 1.45,
                                  ),
                                  children: [
                                    const TextSpan(
                                      text: 'I have read and agree to the ',
                                    ),
                                    TextSpan(
                                      text: 'Trip Logic Terms and Conditions',
                                      style: emphasisStyle,
                                    ),
                                    const TextSpan(text: ' and '),
                                    TextSpan(
                                      text: 'Privacy Policy.',
                                      style: emphasisStyle,
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),

                  const SizedBox(height: 12),

                  LayoutBuilder(
                    builder: (_, constraints) {
                      final stackButtons =
                          constraints.maxWidth < 320 || textScale > 1.25;

                      if (stackButtons) {
                        return Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            declineButton,
                            const SizedBox(height: 10),
                            agreeButton,
                          ],
                        );
                      }

                      return Row(
                        children: [
                          Expanded(flex: 2, child: declineButton),
                          const SizedBox(width: 12),
                          Expanded(flex: 3, child: agreeButton),
                        ],
                      );
                    },
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

class _LegalSectionData {
  const _LegalSectionData({
    required this.number,
    required this.title,
    required this.paragraphs,
  });

  final String number;
  final String title;
  final List<String> paragraphs;
}

const _termsSections = <_LegalSectionData>[
  _LegalSectionData(
    number: '1',
    title: 'Using the App',
    paragraphs: [
      'By using Trip Logic, you agree to use the application responsibly and only for lawful travel-planning purposes.',
      'Trip Logic provides recommendations for attractions, hotels, restaurants, routes, and itinerary plans based on information such as your location, available time, travel partner type, and weather conditions.',
    ],
  ),
  _LegalSectionData(
    number: '2',
    title: 'Recommendations and Guidance',
    paragraphs: [
      'Recommendations are provided for general guidance. Place details, opening hours, and weather conditions can change.',
      'You should verify important information with the relevant venue or official service before travelling.',
    ],
  ),
  _LegalSectionData(
    number: '3',
    title: 'Third-Party Services',
    paragraphs: [
      'Trip Logic depends on third-party services for maps, location data, places, routes, weather, and recommendation explanations.',
      'We are not responsible for errors, service interruptions, delays, losses, or injuries resulting from inaccurate third-party information or decisions made using the application.',
    ],
  ),
  _LegalSectionData(
    number: '4',
    title: 'Your Responsibility',
    paragraphs: [
      'You remain responsible for your travel choices, personal safety, and compliance with local laws and official instructions.',
    ],
  ),
  _LegalSectionData(
    number: '5',
    title: 'Acceptance',
    paragraphs: [
      'By selecting Agree and Continue, you confirm that you have read and accepted these Terms and Conditions and the Privacy Policy.',
    ],
  ),
];

const _privacySections = <_LegalSectionData>[
  _LegalSectionData(
    number: '1',
    title: 'Information Processed',
    paragraphs: [
      'Trip Logic respects your privacy and only processes information required to provide its features.',
      'With your permission, the application can access your current location to provide nearby recommendations, calculate routes, and create suitable itinerary plans.',
    ],
  ),
  _LegalSectionData(
    number: '2',
    title: 'How It Is Used',
    paragraphs: [
      'Trip Logic can also process information you provide, including your available time, travel partner type, and selected destinations.',
      'This information is used to improve recommendations and generate suitable itinerary plans.',
    ],
  ),
  _LegalSectionData(
    number: '3',
    title: 'Location Permission',
    paragraphs: [
      'You can disable location permission at any time through your device settings. Some location-based features may not function correctly without this permission.',
      'Trip Logic does not access your location when it is not needed for an active feature.',
    ],
  ),
  _LegalSectionData(
    number: '4',
    title: 'Sharing With External Services',
    paragraphs: [
      'Limited information can be shared with trusted third-party services when required for place searches, maps, routes, weather information, and recommendation explanations.',
      'Trip Logic does not sell your personal information.',
    ],
  ),
  _LegalSectionData(
    number: '5',
    title: 'Protection and Rights',
    paragraphs: [
      'Reasonable measures are used to protect information processed through the application. However, no mobile application or online service can guarantee complete security.',
      'Sri Lanka’s Personal Data Protection Act provides rights relating to access, correction, and withdrawal of consent for personal-data processing.',
    ],
  ),
];
