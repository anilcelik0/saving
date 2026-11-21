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
}
