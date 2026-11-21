/// Current version of a legal text (privacy policy, KVKK notice) of the app.
class LegalDocument {
  const LegalDocument({
    required this.id,
    required this.kind,
    required this.kindLabel,
    required this.title,
    required this.version,
    required this.requiresAcceptance,
  });

  factory LegalDocument.fromJson(Map<String, dynamic> json) => LegalDocument(
        id: json['id'] as String,
        kind: json['kind'] as String,
        kindLabel: json['kind_label'] as String,
        title: json['title'] as String,
        version: json['version'] as int,
        requiresAcceptance: json['requires_acceptance'] as bool? ?? true,
      );

  final String id;
  final String kind;
  final String kindLabel;
  final String title;
  final int version;
  final bool requiresAcceptance;
}

/// The signed-in user (`/auth/me/`).
class AppUser {
  const AppUser({required this.id, required this.username, required this.isGuest, required this.pendingLegal});

  factory AppUser.fromJson(Map<String, dynamic> json) => AppUser(
        id: json['id'] as String,
        username: json['username'] as String,
        isGuest: json['is_guest'] as bool? ?? false,
        pendingLegal: [
          for (final doc in (json['pending_legal'] as List? ?? const []))
            LegalDocument.fromJson(doc as Map<String, dynamic>),
        ],
      );

  final String id;
  final String username;
  final bool isGuest;

  /// Current legal texts not accepted yet (new versions): asked before continuing.
  final List<LegalDocument> pendingLegal;
}
