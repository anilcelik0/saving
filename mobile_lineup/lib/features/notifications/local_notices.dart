import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

final localNoticesProvider = Provider<LocalNotices>((ref) => LocalNotices());

/// On-device reminders (no server): "energy full" at the time the server gave, "daily puzzle ready" every day at
/// 07:30 Istanbul (the default LINEUP_DAILY_RESET). Inexact timing, so no exact-alarm permission is needed. Each can
/// be turned off in the profile (stored on this device).
class LocalNotices {
  static const prefEnergy = 'notice_energy_full';
  static const prefDaily = 'notice_daily_ready';
  static const _energyId = 1;
  static const _dailyId = 2;

  final _plugin = FlutterLocalNotificationsPlugin();
  Future<void>? _ready;

  Future<void> _init() => _ready ??= () async {
        tzdata.initializeTimeZones();
        await _plugin.initialize(
          settings: const InitializationSettings(android: AndroidInitializationSettings('@mipmap/ic_launcher')),
        );
      }();

  NotificationDetails _details(String channel, String name) => NotificationDetails(
        android: AndroidNotificationDetails(channel, name, importance: Importance.defaultImportance),
      );

  Future<bool> enabled(String key) async {
    try {
      return (await SharedPreferences.getInstance()).getBool(key) ?? true;
    } catch (_) {
      return true;
    }
  }

  Future<void> setEnabled(String key, bool value) async =>
      (await SharedPreferences.getInstance()).setBool(key, value);

  /// [seconds] until energy is full (null = full or unlimited): replaces the pending reminder.
  Future<void> energyFullIn(int? seconds) async {
    try {
      await _init();
      await _plugin.cancel(id: _energyId);
      if (seconds == null || seconds <= 0 || !await enabled(prefEnergy)) return;
      await _plugin.zonedSchedule(
        id: _energyId,
        scheduledDate: tz.TZDateTime.now(tz.UTC).add(Duration(seconds: seconds)),
        notificationDetails: _details('energy', 'Enerji'),
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
        title: 'Enerjin doldu ⚡',
        body: 'Yeni turlar seni bekliyor.',
      );
    } catch (_) {
      // reminders are a nicety: never break the screen for them
    }
  }

  /// Every day at 07:30 Istanbul (or nothing when turned off).
  Future<void> dailyReminder() async {
    try {
      await _init();
      await _plugin.cancel(id: _dailyId);
      if (!await enabled(prefDaily)) return;
      final istanbul = tz.getLocation('Europe/Istanbul');
      final now = tz.TZDateTime.now(istanbul);
      var at = tz.TZDateTime(istanbul, now.year, now.month, now.day, 7, 30);
      if (!at.isAfter(now)) at = at.add(const Duration(days: 1));
      await _plugin.zonedSchedule(
        id: _dailyId,
        scheduledDate: at,
        notificationDetails: _details('daily', 'Günlük bulmaca'),
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
        matchDateTimeComponents: DateTimeComponents.time,
        title: 'Günlük bulmaca hazır 🧩',
        body: 'Bugünün kartlarını sırala, serini sürdür.',
      );
    } catch (_) {}
  }

  /// Logout / new guest: nothing scheduled for the previous user.
  Future<void> cancelAll() async {
    try {
      await _init();
      await _plugin.cancelAll();
    } catch (_) {}
  }
}

/// Watched by the home screen: the daily reminder is (re)scheduled once per app start.
final dailyReminderProvider = FutureProvider<void>((ref) => ref.read(localNoticesProvider).dailyReminder());
