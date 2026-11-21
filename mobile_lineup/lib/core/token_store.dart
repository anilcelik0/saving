import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// JWT pair + guest credentials in encrypted storage (Android Keystore), cached in memory after [load].
///
/// The guest password is the only way back into a guest account once the refresh token expires,
/// so it is kept until the account is linked (Phase 4) or deleted.
class TokenStore {
  TokenStore([FlutterSecureStorage? storage]) : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const _kAccess = 'access';
  static const _kRefresh = 'refresh';
  static const _kGuestUsername = 'guest_username';
  static const _kGuestPassword = 'guest_password';

  String? _access;
  String? _refresh;
  String? _guestUsername;
  String? _guestPassword;
  bool _loaded = false;

  String? get access => _access;
  String? get refresh => _refresh;
  String? get guestUsername => _guestUsername;
  String? get guestPassword => _guestPassword;

  bool get hasGuestCredentials => _guestUsername != null && _guestPassword != null;

  /// Something to open a session with: a refresh token or guest credentials.
  bool get hasSession => _refresh != null || hasGuestCredentials;

  Future<void> load() async {
    if (_loaded) return;
    final all = await _storage.readAll();
    _access = all[_kAccess];
    _refresh = all[_kRefresh];
    _guestUsername = all[_kGuestUsername];
    _guestPassword = all[_kGuestPassword];
    _loaded = true;
  }

  Future<void> saveTokens({required String access, required String refresh}) async {
    _access = access;
    _refresh = refresh;
    await _storage.write(key: _kAccess, value: access);
    await _storage.write(key: _kRefresh, value: refresh);
  }

  Future<void> saveGuest({required String username, required String password}) async {
    _guestUsername = username;
    _guestPassword = password;
    await _storage.write(key: _kGuestUsername, value: username);
    await _storage.write(key: _kGuestPassword, value: password);
  }

  /// Drops the JWT pair but keeps guest credentials (a new login can still open the account).
  Future<void> clearTokens() async {
    _access = null;
    _refresh = null;
    await _storage.delete(key: _kAccess);
    await _storage.delete(key: _kRefresh);
  }

  Future<void> clearAll() async {
    _access = _refresh = _guestUsername = _guestPassword = null;
    await _storage.deleteAll();
  }
}
