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

/// A registered account was used here but has no session (logged out, frozen, or the session expired).
class SessionNeedsLogin extends Session {
  const SessionNeedsLogin(this.identifier);

  final String identifier;
}

/// Signed in, but the account is frozen or waiting for deletion: reopen it or log out.
class SessionInactive extends Session {
  const SessionInactive(this.user);

  final AppUser user;
}

class SessionReady extends Session {
  const SessionReady(this.user);

  final AppUser user;
}

final sessionProvider = AsyncNotifierProvider<SessionController, Session>(SessionController.new);

/// Id of the signed-in user; data providers watch it so another account (login, new guest) refetches them.
final currentUserIdProvider = Provider<String?>((ref) => switch (ref.watch(sessionProvider).value) {
      SessionReady(:final user) => user.id,
      _ => null,
    });

/// Start-up flow: stored session → /auth/me/; a registered account without a session → login; otherwise legal
/// texts → guest account. Loading and errors are the AsyncValue's own states (start screen: spinner / retry).
class SessionController extends AsyncNotifier<Session> {
  @override
  Future<Session> build() async {
    final auth = ref.read(authServiceProvider);
    if (await auth.hasSession()) {
      try {
        return _fromUser(await auth.me());
      } on SessionLostException {
        // the stored session can't be opened any more: ask a registered account to log in, else a new guest
      }
    }
    final account = auth.account;
    if (account != null) return SessionNeedsLogin(account);
    final required = (await auth.legalDocuments()).where((doc) => doc.requiresAcceptance).toList();
    if (required.isEmpty) return SessionReady(await auth.createGuest(const []));
    return SessionNeedsConsent(required, newGuest: true);
  }

  Session _fromUser(AppUser user) {
    if (!user.isActive) return SessionInactive(user);
    return user.pendingLegal.isEmpty ? SessionReady(user) : SessionNeedsConsent(user.pendingLegal, newGuest: false);
  }

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

  /// Errors (wrong password, offline) are thrown to the login screen; the state changes only on success.
  Future<void> login(String identifier, String password) async {
    final user = await ref.read(authServiceProvider).login(identifier, password);
    state = AsyncData(_fromUser(user));
  }

  /// After the guest was claimed / the user changed: show the fresh user.
  void updateUser(AppUser user) => state = AsyncData(_fromUser(user));

  Future<void> reactivate() async {
    final user = await ref.read(authServiceProvider).reactivate();
    state = AsyncData(_fromUser(user));
  }

  /// Registered accounts only (a guest has no way back in).
  Future<void> logout() async {
    final auth = ref.read(authServiceProvider);
    await auth.logout();
    state = AsyncData(SessionNeedsLogin(auth.account ?? ''));
  }

  /// Freeze: signed out everywhere; logging in again offers to reopen.
  Future<void> deactivate(String password) async {
    final auth = ref.read(authServiceProvider);
    await auth.deactivate(password);
    state = AsyncData(SessionNeedsLogin(auth.account ?? ''));
  }

  /// Deletion requested: this device starts over with a new guest.
  Future<void> requestDeletion(String password) async {
    await ref.read(authServiceProvider).requestDeletion(password);
    ref.invalidateSelf();
  }

  /// From the login screen: forget the account on this device and start as a new guest.
  Future<void> startAsGuest() async {
    await ref.read(authServiceProvider).forgetDevice();
    ref.invalidateSelf();
  }

  void retry() => ref.invalidateSelf();
}
