import 'package:flutter/foundation.dart';

/// Client app slug on the shared backend (accounts.ClientApp). Sent on guest creation and login.
const String appSlug = 'lineup';

/// Optional override: flutter run --dart-define=API_URL=http://192.168.1.10/api/v1
const String _apiUrlOverride = String.fromEnvironment('API_URL');
const String _productionUrl = 'https://appmanager.com.tr/api/v1';
// 10.0.2.2 is the host PC as seen from the Android emulator (dev backend behind nginx on port 80).
const String _emulatorUrl = 'http://10.0.2.2/api/v1';

/// Debug/profile builds talk to the dev backend, release builds to production.
String get apiBaseUrl {
  if (_apiUrlOverride.isNotEmpty) return _apiUrlOverride;
  return kReleaseMode ? _productionUrl : _emulatorUrl;
}

/// Rewarded ad unit: Google's public test unit in debug/profile (always fills, never pays); release builds need
/// the real unit: flutter build appbundle --dart-define=ADMOB_REWARDED_UNIT=ca-app-pub-.../... (Phase 9).
const String _rewardedUnitOverride = String.fromEnvironment('ADMOB_REWARDED_UNIT');
const String _rewardedTestUnit = 'ca-app-pub-3940256099942544/5224354917';

/// Empty = no rewarded ads in this build.
String get rewardedAdUnit {
  if (_rewardedUnitOverride.isNotEmpty) return _rewardedUnitOverride;
  return kReleaseMode ? '' : _rewardedTestUnit;
}
