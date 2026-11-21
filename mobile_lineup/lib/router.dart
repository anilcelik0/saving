import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'features/dev/dev_tools_screen.dart';
import 'features/home/home_screen.dart';
import 'features/session/consent_screen.dart';
import 'features/session/session_controller.dart';
import 'features/session/start_screen.dart';
import 'features/streak/streak_screen.dart';
import 'features/timeline/timeline_screen.dart';

/// Routes follow the session: loading/error → `/`, legal texts → `/consent`, signed in → `/home` (and below).
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
        SessionReady() => '/home',
      };
      if (target == '/home' && state.matchedLocation.startsWith('/home')) return null;
      return state.matchedLocation == target ? null : target;
    },
    routes: [
      GoRoute(path: '/', builder: (context, state) => const StartScreen()),
      GoRoute(path: '/consent', builder: (context, state) => const ConsentScreen()),
      GoRoute(
        path: '/home',
        builder: (context, state) => const HomeScreen(),
        routes: [
          GoRoute(path: 'dev', builder: (context, state) => const DevToolsScreen()),
          GoRoute(path: 'timeline', builder: (context, state) => const TimelineScreen()),
          GoRoute(path: 'streak', builder: (context, state) => const StreakScreen()),
        ],
      ),
    ],
  );
});
