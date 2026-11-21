import 'dart:async';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/services.dart';
import 'package:google_mobile_ads/google_mobile_ads.dart';
import 'package:material_ui/material_ui.dart';

import '../../config.dart';

/// Phase 0.6 plugin proof (debug builds only): a rewarded TEST ad and an FCM push.
/// Real rewards are granted by the server after AdMob's server-side verification (Phase 5);
/// the client callback below is only for the UI.
class DevToolsScreen extends StatefulWidget {
  const DevToolsScreen({super.key});

  @override
  State<DevToolsScreen> createState() => _DevToolsScreenState();
}

class _DevToolsScreenState extends State<DevToolsScreen> {
  // Google's public test unit for rewarded ads on Android (always fills, never pays).
  static const _rewardedTestUnit = 'ca-app-pub-3940256099942544/5224354917';
  // `manage.py send_test_push lineup` sends to this topic.
  static const _devTopic = '$appSlug-dev';

  String _adStatus = 'Hazır';
  bool _adBusy = false;
  String _pushStatus = 'Hazırlanıyor...';
  String? _token;
  StreamSubscription<RemoteMessage>? _onMessage;
  StreamSubscription<String>? _onRegistered;

  @override
  void initState() {
    super.initState();
    _setupPush();
  }

  @override
  void dispose() {
    _onMessage?.cancel();
    _onRegistered?.cancel();
    super.dispose();
  }

  Future<void> _setupPush() async {
    try {
      final messaging = FirebaseMessaging.instance;
      final settings = await messaging.requestPermission(); // Android 13+: system permission dialog
      // The device token arrives on onRegistered after register() (Phase 6 sends it to the server).
      _onRegistered = messaging.onRegistered.listen((token) {
        if (mounted) setState(() => _token = token);
      });
      await messaging.register();
      await messaging.subscribeToTopic(_devTopic);
      // While the app is open Android shows nothing by itself, so show it here.
      _onMessage = FirebaseMessaging.onMessage.listen((message) {
        final n = message.notification;
        if (mounted) setState(() => _pushStatus = 'Uygulama açıkken geldi: ${n?.title} · ${n?.body}');
      });
      if (!mounted) return;
      setState(() => _pushStatus = 'İzin: ${settings.authorizationStatus.name} · konu: $_devTopic');
    } catch (e) {
      if (mounted) setState(() => _pushStatus = 'Hata: $e');
    }
  }

  void _setAd(String status, {bool busy = false}) {
    if (!mounted) return;
    setState(() {
      _adStatus = status;
      _adBusy = busy;
    });
  }

  void _showRewardedAd() {
    _setAd('Reklam yükleniyor...', busy: true);
    RewardItem? earned;
    RewardedAd.load(
      adUnitId: _rewardedTestUnit,
      request: const AdRequest(),
      rewardedAdLoadCallback: RewardedAdLoadCallback(
        onAdLoaded: (ad) {
          ad.fullScreenContentCallback = FullScreenContentCallback(
            onAdDismissedFullScreenContent: (ad) {
              ad.dispose();
              _setAd(earned == null ? 'Reklam ödülsüz kapatıldı' : 'Ödül kazanıldı: ${earned!.amount} ${earned!.type}');
            },
            onAdFailedToShowFullScreenContent: (ad, error) {
              ad.dispose();
              _setAd('Gösterilemedi: ${error.message}');
            },
          );
          ad.show(onUserEarnedReward: (ad, reward) => earned = reward);
        },
        onAdFailedToLoad: (error) => _setAd('Yüklenemedi: ${error.message}'),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Geliştirici araçları')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Ödüllü reklam (test)', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  Text(_adStatus),
                  const SizedBox(height: 12),
                  FilledButton(
                    onPressed: _adBusy ? null : _showRewardedAd,
                    child: const Text('Reklam izle'),
                  ),
                ],
              ),
            ),
          ),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Push bildirimi (FCM)', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  Text(_pushStatus),
                  if (_token != null) ...[
                    const SizedBox(height: 8),
                    SelectableText('Token: $_token', maxLines: 3, style: Theme.of(context).textTheme.bodySmall),
                    TextButton.icon(
                      onPressed: () => Clipboard.setData(ClipboardData(text: _token!)),
                      icon: const Icon(Icons.copy),
                      label: const Text('Token kopyala'),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
