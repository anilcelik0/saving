import 'package:google_fonts/google_fonts.dart';
import 'package:material_ui/material_ui.dart';

/// "Gündüz" palette from the Phase 8 design canvas (light background, blue primary, orange accent).
abstract final class LU {
  static const bg = Color(0xFFF2F4F8);
  static const surface = Color(0xFFFFFFFF);
  static const ink = Color(0xFF141A2E);
  static const muted = Color(0xFF4A5470);
  static const line = Color(0xFFDCE1EC);
  static const empty = Color(0xFFE4E8F0);

  static const primary = Color(0xFF2D5BFF);
  static const primarySoft = Color(0xFFE6ECFF);
  static const onPrimarySoft = Color(0xFF1A36A8);

  /// Fills (energy, axis); [accentText] for text on light surfaces, [accentStrong] under white text.
  static const accent = Color(0xFFE8701F);
  static const accentText = Color(0xFFB4520F);
  static const accentStrong = Color(0xFFC2410C);
  static const accentSoft = Color(0xFFFFEBDD);
  static const onAccentSoft = Color(0xFF8A3A08);

  /// Daily puzzle marks.
  static const right = Color(0xFF1F9D55);
  static const near = Color(0xFFF2B53A);
  static const wrong = Color(0xFFC93C3C);

  static const radius = 16.0;
  static const shadow = [BoxShadow(color: Color(0x14141A2E), blurRadius: 3, offset: Offset(0, 1))];
  static const liftShadow = [BoxShadow(color: Color(0x47141A2E), blurRadius: 28, offset: Offset(0, 12))];
}

/// Headings and numbers (Space Grotesk); body text uses Inter through the theme.
TextStyle display(double size, {Color? color, FontWeight weight = FontWeight.w700}) =>
    GoogleFonts.spaceGrotesk(fontSize: size, fontWeight: weight, color: color ?? LU.ink, height: 1.1);

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(seedColor: LU.primary).copyWith(
    primary: LU.primary,
    onPrimary: Colors.white,
    primaryContainer: LU.primarySoft,
    onPrimaryContainer: LU.onPrimarySoft,
    secondary: LU.accentStrong,
    onSecondary: Colors.white,
    secondaryContainer: LU.accentSoft,
    onSecondaryContainer: LU.onAccentSoft,
    surface: LU.bg,
    onSurface: LU.ink,
    onSurfaceVariant: LU.muted,
    surfaceContainerLowest: LU.surface,
    surfaceContainerLow: LU.surface,
    surfaceContainer: LU.surface,
    outlineVariant: LU.line,
    error: LU.wrong,
  );
  final base = ThemeData(colorScheme: scheme);
  final text = GoogleFonts.interTextTheme(base.textTheme)
      .copyWith(
        headlineMedium: display(28),
        headlineSmall: display(24),
        titleLarge: display(20),
      )
      .apply(bodyColor: LU.ink, displayColor: LU.ink);
  final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(LU.radius));
  final label = GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w600);
  return base.copyWith(
    scaffoldBackgroundColor: LU.bg,
    textTheme: text,
    appBarTheme: AppBarTheme(
      backgroundColor: LU.bg,
      foregroundColor: LU.ink,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      titleTextStyle: display(20),
    ),
    cardTheme: CardThemeData(color: LU.surface, elevation: 0, shape: shape),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(minimumSize: const Size(64, 52), shape: shape, textStyle: label),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(minimumSize: const Size(64, 52), shape: shape, textStyle: label),
    ),
    snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
  );
}

/// Round white 44 px icon button used in screen headers (back, archive, ...).
class CircleIconButton extends StatelessWidget {
  const CircleIconButton({super.key, required this.icon, required this.tooltip, required this.onPressed});

  final IconData icon;
  final String tooltip;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => Tooltip(
        message: tooltip,
        child: Material(
          color: LU.surface,
          shape: const CircleBorder(),
          elevation: 0,
          child: InkWell(
            customBorder: const CircleBorder(),
            onTap: onPressed,
            child: Container(
              width: 44,
              height: 44,
              decoration: const BoxDecoration(shape: BoxShape.circle, boxShadow: LU.shadow),
              child: Icon(icon, size: 22, color: LU.ink),
            ),
          ),
        ),
      );
}
