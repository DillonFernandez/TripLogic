import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:trip_logic/theme/app_colors.dart';

final ValueNotifier<ThemeMode> appThemeModeNotifier = ValueNotifier(
  ThemeMode.system,
);

Future<ThemeMode> loadThemeModePreference() async {
  final prefs = await SharedPreferences.getInstance();
  final savedValue = prefs.getString('app_theme_mode');

  switch (savedValue) {
    case 'light':
      return ThemeMode.light;
    case 'dark':
      return ThemeMode.dark;
    case 'system':
    default:
      return ThemeMode.system;
  }
}

Future<void> saveThemeModePreference(ThemeMode mode) async {
  final prefs = await SharedPreferences.getInstance();

  switch (mode) {
    case ThemeMode.light:
      await prefs.setString('app_theme_mode', 'light');
      break;
    case ThemeMode.dark:
      await prefs.setString('app_theme_mode', 'dark');
      break;
    case ThemeMode.system:
      await prefs.setString('app_theme_mode', 'system');
      break;
  }
}

class AppTheme {
  const AppTheme._();

  static ThemeData get lightTheme {
    final colorScheme = ColorScheme.fromSeed(
      seedColor: AppColors.primary,
      brightness: Brightness.light,
      primary: AppColors.primary,
      onPrimary: AppColors.white,
      surface: AppColors.lightSurface,
      onSurface: AppColors.lightTextPrimary,
      onSurfaceVariant: AppColors.lightTextSecondary,
      secondary: AppColors.primary,
      onSecondary: AppColors.white,
      surfaceContainerLow: AppColors.lightPanel,
      outlineVariant: AppColors.lightTextSecondary.withValues(alpha: 0.32),
    );

    final baseTextTheme = Typography.material2021().black;

    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: AppColors.lightSurface,
      textTheme: baseTextTheme.copyWith(
        headlineMedium: baseTextTheme.headlineMedium?.copyWith(
          color: AppColors.lightTextPrimary,
          fontSize: 26,
          fontWeight: FontWeight.w700,
          height: 1.04,
        ),
        bodySmall: baseTextTheme.bodySmall?.copyWith(
          color: AppColors.lightTextSecondary,
          fontSize: 12,
          height: 1.35,
          fontWeight: FontWeight.w400,
        ),
      ),
    );
  }

  static ThemeData get darkTheme {
    final colorScheme = ColorScheme.fromSeed(
      seedColor: AppColors.primary,
      brightness: Brightness.dark,
      primary: AppColors.primary,
      onPrimary: AppColors.white,
      surface: AppColors.darkSurface,
      onSurface: AppColors.darkTextPrimary,
      onSurfaceVariant: AppColors.darkTextSecondary,
      secondary: AppColors.primary,
      onSecondary: AppColors.white,
      surfaceContainerLow: AppColors.darkPanel,
      outlineVariant: AppColors.darkTextSecondary.withValues(alpha: 0.32),
    );

    final baseTextTheme = Typography.material2021().white;

    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: AppColors.darkSurface,
      textTheme: baseTextTheme.copyWith(
        headlineMedium: baseTextTheme.headlineMedium?.copyWith(
          color: AppColors.darkTextPrimary,
          fontSize: 26,
          fontWeight: FontWeight.w700,
          height: 1.04,
        ),
        bodySmall: baseTextTheme.bodySmall?.copyWith(
          color: AppColors.darkTextSecondary,
          fontSize: 12,
          height: 1.35,
          fontWeight: FontWeight.w400,
        ),
      ),
    );
  }
}
