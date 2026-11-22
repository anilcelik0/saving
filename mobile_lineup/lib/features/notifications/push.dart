import 'dart:async';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';
import '../../router.dart';
import '../session/session_controller.dart';

/// SnackBars outside any screen's context (pushes received while the app is open).
final messengerKey = GlobalKey<ScaffoldMessengerState>();

final pushProvider = Provider<PushService>((ref) {
  final service = PushService(ref);
  ref.onDispose(service.dispose);
  return service;
});

/// Watched by the app: registers this device for the signed-in user (and again when the user changes).
final pushSessionProvider = Provider<void>((ref) {
  final userId = ref.watch(currentUserIdProvider);
  if (userId != null) unawaited(ref.read(pushProvider).start(userId));
});

/// FCM for the signed-in user: device token → server (`notifications/devices/`), a tapped push opens its screen
/// (data {"type": "challenge", "code": ...}), a push while the app is open shows a SnackBar.
class PushService {
  PushService(this._ref);

  final Ref _ref;
  String? _userId;
  String? _token;
  final _subscriptions = <StreamSubscription<Object?>>[];

  ApiClient get _api => _ref.read(apiClientProvider);

  Future<void> start(String userId) async {
    if (_userId == userId) return;
    _userId = userId;
    try {
      final messaging = FirebaseMessaging.instance;
      await messaging.requestPermission(); // Android 13+: the system asks once
      if (_subscriptions.isEmpty) {
        _subscriptions
          ..add(messaging.onRegistered.listen(_register))
          ..add(FirebaseMessaging.onMessageOpenedApp.listen(_open))
          ..add(FirebaseMessaging.onMessage.listen(_showInApp));
        final initial = await messaging.getInitialMessage(); // the app was started by tapping a push
        if (initial != null) _open(initial);
      }
      final known = _token;
      if (known != null) await _register(known); // another user signed in on this device: move the token now
      await messaging.register(); // the token arrives on onRegistered
    } catch (_) {
      // no Play services / Firebase not configured: the game works without push
    }
  }

  Future<void> _register(String token) async {
    _token = token;
    if (_userId == null) return;
    try {
      await _api.post('notifications/devices/', data: {'token': token, 'platform': 'android'});
    } on ApiException {
      // retried on the next start
    }
  }

  /// Before logout / freeze / deletion (needs the session): this device stops getting the user's pushes.
  Future<void> stop() async {
    final token = _token;
    _userId = null;
    if (token == null) return;
    try {
      await _api.delete('notifications/devices/', data: {'token': token});
    } on ApiException {
      // the server drops dead tokens on the next send anyway
    }
  }

  void _open(RemoteMessage message) {
    final code = message.data['code'];
    if (message.data['type'] == 'challenge' && code is String) {
      _ref.read(routerProvider).go('/home/challenges/$code');
    }
  }

  void _showInApp(RemoteMessage message) {
    final n = message.notification;
    if (n == null) return;
    messengerKey.currentState?.showSnackBar(SnackBar(
      content: Text([n.title, n.body].whereType<String>().join(' · ')),
      behavior: SnackBarBehavior.floating,
      duration: const Duration(seconds: 6),
      action: message.data['type'] == 'challenge' ? SnackBarAction(label: 'Aç', onPressed: () => _open(message)) : null,
    ));
  }

  void dispose() {
    for (final s in _subscriptions) {
      s.cancel();
    }
  }
}
