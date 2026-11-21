import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/models.dart';
import '../../core/providers.dart';

/// Where the app stands at start-up. The router redirects on it (see router.dart).
sealed class Session {
  const Session();
}

/// Legal texts must be accepted first: before creating a guest ([newGuest]) or after a new version.
class SessionNeedsConsent extends Session {
  const SessionNeedsConsent(this.documents, {required this.newGuest});

  final List<LegalDocument> documents;
  final bool newGuest;
}

class SessionReady extends Session {
  const SessionReady(this.user);

  final AppUser user;
}

final sessionProvider = AsyncNotifierProvider<SessionController, Session>(SessionController.new);

/// Start-up flow: stored session → /auth/me/; otherwise legal texts → guest account.
/// Loading and errors are the AsyncValue's own states (start screen shows a spinner or a retry button).
class SessionController extends AsyncNotifier<Session> {
  @override
  Future<Session> build() async {
    final auth = ref.read(authServiceProvider);
    if (await auth.hasSession()) {
      try {
        return _fromUser(await auth.me());
      } on SessionLostException {
        // the stored account can't be opened any more: continue as a new guest
      }
    }
    final required = (await auth.legalDocuments()).where((doc) => doc.requiresAcceptance).toList();
    if (required.isEmpty) return SessionReady(await auth.createGuest(const []));
    return SessionNeedsConsent(required, newGuest: true);
  }

  Session _fromUser(AppUser user) =>
      user.pendingLegal.isEmpty ? SessionReady(user) : SessionNeedsConsent(user.pendingLegal, newGuest: false);

  /// User accepted every listed document.
  Future<void> accept() async {
    final current = state.value;
    if (current is! SessionNeedsConsent) return;
    final auth = ref.read(authServiceProvider);
    final ids = [for (final doc in current.documents) doc.id];
    state = const AsyncLoading();
    state = await AsyncValue.guard(() async =>
        _fromUser(current.newGuest ? await auth.createGuest(ids) : await auth.acceptConsents(ids)));
  }

  void retry() => ref.invalidateSelf();
}
