import '../../config.dart';
import '../../core/api_client.dart';
import '../../core/models.dart';
import '../../core/token_store.dart';

/// Account endpoints of the shared `accounts` app (`/api/v1/auth/...`, `/api/v1/legal/<app>/...`).
class AuthService {
  AuthService(this._api, this._tokens);

  final ApiClient _api;
  final TokenStore _tokens;

  /// A stored refresh token or guest credentials exist on this device.
  Future<bool> hasSession() async {
    await _tokens.load();
    return _tokens.hasSession;
  }

  /// Login name of the registered account last used on this device (null = guest only / never).
  String? get account => _tokens.account;

  /// Stored guest password: confirms account actions for a guest (who never typed a password).
  String? get guestPassword => _tokens.guestPassword;

  Future<AppUser> me() async => AppUser.fromJson(await _api.get('auth/me/'));

  Future<List<LegalDocument>> legalDocuments() async {
    final data = await _api.get('legal/$appSlug/', auth: false) as List;
    return [for (final doc in data) LegalDocument.fromJson(doc as Map<String, dynamic>)];
  }

  /// Markdown text of the current version of a document.
  Future<String> legalBody(String kind) async {
    final data = await _api.get('legal/$appSlug/$kind/', auth: false);
    return data['body'] as String;
  }

  /// First launch: the server creates a guest and returns its generated password once; both are stored.
  Future<AppUser> createGuest(List<String> acceptedDocumentIds) async {
    final data = await _api.post(
      'auth/guest/',
      data: {'app': appSlug, 'accepted_documents': acceptedDocumentIds},
      auth: false,
    );
    final credentials = data['credentials'];
    await _tokens.saveGuest(username: credentials['username'], password: credentials['password']);
    await _tokens.saveTokens(access: data['access'], refresh: data['refresh']);
    return AppUser.fromJson(data['user']);
  }

  /// Accept new versions of legal texts for an existing user.
  Future<AppUser> acceptConsents(List<String> documentIds) async {
    await _api.post('auth/consents/', data: {'documents': documentIds});
    return me();
  }

  /// Email or username + password. Replaces the session on this device (a guest on it is left behind).
  Future<AppUser> login(String identifier, String password) async {
    final data = await _api.post(
      'auth/login/',
      data: {'app': appSlug, 'identifier': identifier, 'password': password},
      auth: false,
    );
    await _tokens.saveTokens(access: data['access'], refresh: data['refresh']);
    await _tokens.saveAccount(identifier.trim().toLowerCase());
    return AppUser.fromJson(data['user']);
  }

  /// The guest becomes a regular account (same data); afterwards it logs in with email + password.
  Future<AppUser> claim({required String email, required String password, String username = ''}) async {
    final data = await _api.post('auth/guest/claim/', data: {'email': email, 'password': password, 'username': username});
    await _tokens.saveTokens(access: data['access'], refresh: data['refresh']);
    final user = AppUser.fromJson(data['user']);
    await _tokens.saveAccount(user.email);
    return user;
  }

  /// Signs this device out (the refresh token is blacklisted); the login name is kept for the form.
  Future<void> logout() async {
    final refresh = _tokens.refresh;
    if (refresh != null) {
      try {
        await _api.post('auth/logout/', data: {'refresh': refresh}, auth: false);
      } on ApiException {
        // offline or already invalid: forget it locally anyway
      }
    }
    await _tokens.clearTokens();
  }

  Future<AppUser> reactivate() async => AppUser.fromJson(await _api.post('auth/account/reactivate/'));

  /// Freeze (data kept, log in again to reopen). Every device is signed out.
  Future<void> deactivate(String password) async {
    await _api.post('auth/account/deactivate/', data: {'password': password});
    await _tokens.clearTokens();
  }

  /// Deletion after the grace period. Everything on this device is forgotten (a new guest starts).
  Future<void> requestDeletion(String password) async {
    await _api.post('auth/account/delete/', data: {'password': password});
    await _tokens.clearAll();
  }

  /// Forget every stored credential (the next start creates a new guest).
  Future<void> forgetDevice() => _tokens.clearAll();
}
