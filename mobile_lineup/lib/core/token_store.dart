import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// JWT pair + guest credentials in encrypted storage (Android Keystore), cached in memory after [load].
///
/// The guest password is the only way back into a guest account once the refresh token expires,
/// so it is kept until the account is claimed (email + password) or deleted. A registered account keeps only its
/// login name ([account]) so a lost session asks for the password instead of starting a new guest.
class TokenStore {
  TokenStore([FlutterSecureStorage? storage]) : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const _kAccess = 'access';
  static const _kRefresh = 'refresh';
  static const _kGuestUsername = 'guest_username';
  static const _kGuestPassword = 'guest_password';
  static const _kAccount = 'account';

  String? _access;
  String? _refresh;
  String? _guestUsername;
  String? _guestPassword;
  String? _account;
  bool _loaded = false;

  String? get access => _access;
  String? get refresh => _refresh;
  String? get guestUsername => _guestUsername;
  String? get guestPassword => _guestPassword;

  /// Email / username of a registered account used on this device (kept after logout to fill the login form).
  String? get account => _account;

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
    _account = all[_kAccount];
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

  /// A registered account is signed in: the guest credentials are gone (the guest was claimed or left).
  Future<void> saveAccount(String identifier) async {
    _account = identifier;
    _guestUsername = _guestPassword = null;
    await _storage.write(key: _kAccount, value: identifier);
    await _storage.delete(key: _kGuestUsername);
    await _storage.delete(key: _kGuestPassword);
  }

  /// Drops the JWT pair but keeps guest credentials (a new login can still open the account).
  Future<void> clearTokens() async {
    _access = null;
    _refresh = null;
    await _storage.delete(key: _kAccess);
    await _storage.delete(key: _kRefresh);
  }

  Future<void> clearAll() async {
    _access = _refresh = _guestUsername = _guestPassword = _account = null;
    await _storage.deleteAll();
  }
}
