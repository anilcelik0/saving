import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'features/billing/pro_screen.dart';
import 'features/daily/archive_screen.dart';
import 'features/daily/daily_screen.dart';
import 'features/dev/dev_tools_screen.dart';
import 'features/home/home_screen.dart';
import 'features/profile/claim_screen.dart';
import 'features/profile/profile_screen.dart';
import 'features/session/consent_screen.dart';
import 'features/session/inactive_screen.dart';
import 'features/session/login_screen.dart';
import 'features/session/session_controller.dart';
import 'features/session/start_screen.dart';
import 'features/streak/streak_screen.dart';
import 'features/timeline/timeline_screen.dart';

/// Routes follow the session: loading/error → `/`, legal texts → `/consent` (a new device may open `/login` from
/// there), registered account without a session → `/login`, frozen account → `/inactive`, signed in → `/home`.
final routerProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier(0);
  ref.listen(sessionProvider, (_, _) => refresh.value++);
  ref.onDispose(refresh.dispose);

  return GoRouter(
    initialLocation: '/',
    refreshListenable: refresh,
    redirect: (context, state) {
      final session = ref.read(sessionProvider);
      final value = session.isLoading || session.hasError ? null : session.value;
      final target = switch (value) {
        null => '/',
        SessionNeedsConsent() => '/consent',
        SessionNeedsLogin() => '/login',
        SessionInactive() => '/inactive',
        SessionReady() => '/home',
      };
      if (target == '/home' && state.matchedLocation.startsWith('/home')) return null;
      if (value is SessionNeedsConsent && value.newGuest && state.matchedLocation == '/login') return null;
      return state.matchedLocation == target ? null : target;
    },
    routes: [
      GoRoute(path: '/', builder: (context, state) => const StartScreen()),
      GoRoute(path: '/consent', builder: (context, state) => const ConsentScreen()),
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
      GoRoute(path: '/inactive', builder: (context, state) => const InactiveScreen()),
      GoRoute(
        path: '/home',
        builder: (context, state) => const HomeScreen(),
        routes: [
          GoRoute(path: 'dev', builder: (context, state) => const DevToolsScreen()),
          GoRoute(path: 'timeline', builder: (context, state) => const TimelineScreen()),
          GoRoute(path: 'streak', builder: (context, state) => const StreakScreen()),
          GoRoute(path: 'daily', builder: (context, state) => const DailyScreen()),
          GoRoute(
            path: 'archive',
            builder: (context, state) => const ArchiveScreen(),
            routes: [
              GoRoute(
                path: ':number',
                builder: (context, state) => DailyScreen(number: int.parse(state.pathParameters['number']!)),
              ),
            ],
          ),
          GoRoute(path: 'pro', builder: (context, state) => const ProScreen()),
          GoRoute(path: 'login', builder: (context, state) => const LoginScreen(fromGuest: true)),
          GoRoute(
            path: 'profile',
            builder: (context, state) => const ProfileScreen(),
            routes: [GoRoute(path: 'claim', builder: (context, state) => const ClaimScreen())],
          ),
        ],
      ),
    ],
  );
});
