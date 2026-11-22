import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_mobile_ads/google_mobile_ads.dart';

import '../../config.dart';
import '../../core/api_client.dart';
import '../../core/providers.dart';

/// Server reward kinds (shared billing app, registered by lineup_games).
const rewardEnergy = 'lineup.energy';
const rewardContinue = 'lineup.continue';

final rewardAdsProvider = Provider<RewardAds>((ref) => RewardAds(ref.watch(apiClientProvider)));

/// Rewarded ads, granted only by the server (CLAUDE.md rule 8 / brief: never on the client's word):
/// 1. ask the server for a reward intent (it checks the reward makes sense + the daily ad cap),
/// 2. show the ad with SSV options (user id + intent id as custom data),
/// 3. AdMob calls the server, which grants the reward; we poll the intent until it is granted.
/// Debug builds use Google's test unit, whose callbacks never reach a dev PC: the DEBUG-only dev grant stands in.
class RewardAds {
  RewardAds(this._api);

  final ApiClient _api;
  bool _consentChecked = false;

  bool get available => rewardedAdUnit.isNotEmpty;

  /// True when the reward was granted; false when the ad was closed before the reward. Errors: ApiException.
  Future<bool> watch(String kind, {String ref = ''}) async {
    if (!available) throw ApiException('Reklamlar bu sürümde kapalı.', code: 'ads_unavailable');
    final intent = await _api.post('billing/rewards/', data: {'kind': kind, 'ref': ref});
    await _ensureConsent();
    final earned = await _show(intent['user_id'] as String, intent['custom_data'] as String);
    if (!earned) return false;
    return _waitForGrant(intent['id'] as String);
  }

  /// UMP (GDPR): asks EEA/UK users once per app start before the first ad; elsewhere it returns at once.
  Future<void> _ensureConsent() async {
    if (_consentChecked) return;
    _consentChecked = true;
    final done = Completer<void>();
    ConsentInformation.instance.requestConsentInfoUpdate(
      ConsentRequestParameters(),
      () => ConsentForm.loadAndShowConsentFormIfRequired((_) => done.complete()),
      (_) => done.complete(), // no consent info (offline / not configured yet): AdMob decides per request
    );
    await done.future;
  }

  /// "Reklam gizlilik ayarları" in the profile is required where UMP applies.
  Future<bool> privacyOptionsRequired() async {
    await _ensureConsent();
    return await ConsentInformation.instance.getPrivacyOptionsRequirementStatus() ==
        PrivacyOptionsRequirementStatus.required;
  }

  Future<void> showPrivacyOptions() => ConsentForm.showPrivacyOptionsForm((_) {});

  Future<bool> _show(String userId, String customData) {
    final done = Completer<bool>();
    var earned = false;
    RewardedAd.load(
      adUnitId: rewardedAdUnit,
      request: const AdRequest(),
      rewardedAdLoadCallback: RewardedAdLoadCallback(
        onAdLoaded: (ad) async {
          await ad.setServerSideOptions(ServerSideVerificationOptions(userId: userId, customData: customData));
          ad.fullScreenContentCallback = FullScreenContentCallback(
            onAdDismissedFullScreenContent: (ad) {
              ad.dispose();
              if (!done.isCompleted) done.complete(earned);
            },
            onAdFailedToShowFullScreenContent: (ad, error) {
              ad.dispose();
              if (!done.isCompleted) done.completeError(ApiException('Reklam gösterilemedi.', code: 'ad_show'));
            },
          );
          await ad.show(onUserEarnedReward: (_, _) => earned = true);
        },
        onAdFailedToLoad: (error) {
          if (!done.isCompleted) {
            done.completeError(ApiException('Şu an reklam yok. Biraz sonra tekrar dene.', code: 'ad_load'));
          }
        },
      ),
    );
    return done.future;
  }

  Future<bool> _waitForGrant(String intentId) async {
    if (!kReleaseMode) {
      try {
        return _granted(await _api.post('billing/dev/rewards/$intentId/grant/'));
      } on ApiException catch (e) {
        if (e.statusCode != 404) rethrow; // a non-DEBUG backend: wait for the real callback below
      }
    }
    for (var i = 0; i < 15; i++) {
      await Future<void>.delayed(const Duration(seconds: 2));
      final intent = await _api.get('billing/rewards/$intentId/');
      if (intent['status'] != 'pending') return _granted(intent);
    }
    throw ApiException('Ödül henüz onaylanmadı; birkaç dakika içinde hesabına geçer.', code: 'reward_pending');
  }

  bool _granted(dynamic intent) {
    if (intent['status'] == 'granted') return true;
    final detail = intent['detail'] as String?;
    throw ApiException(detail == null || detail.isEmpty ? 'Ödül verilemedi.' : 'Ödül verilemedi ($detail).',
        code: 'reward_rejected');
  }
}
