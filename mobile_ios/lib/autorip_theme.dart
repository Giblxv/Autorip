import 'package:flutter/material.dart';

/// Shared Looney palette for the real connection form and web panel shell.
abstract final class AutoRipTheme {
  static const canvas = Color(0xFF0D071A);
  static const surface = Color(0xFF180E2E);
  static const raised = Color(0xFF241545);
  static const outline = Color(0xFF655080);
  static const ink = Color(0xFF05020A);
  static const cyan = Color(0xFF00F5D4);
  static const pink = Color(0xFFFF2A85);
  static const yellow = Color(0xFFFFE600);
  static const text = Color(0xFFFFFDF7);
  static const muted = Color(0xFFCBBBE8);

  static ThemeData get dark => ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(
      seedColor: cyan,
      brightness: Brightness.dark,
    ).copyWith(
      primary: cyan,
      onPrimary: ink,
      surface: surface,
      onSurface: text,
      error: const Color(0xFFFF80B4),
    ),
    scaffoldBackgroundColor: canvas,
    appBarTheme: const AppBarTheme(
      backgroundColor: canvas,
      foregroundColor: text,
      centerTitle: false,
    ),
  );
}
