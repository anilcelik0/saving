import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models.dart';
import '../../core/providers.dart';
import '../session/session_controller.dart';

/// `GET lineup/games/profile/`: stats per mode.
class ProfileStats {
  const ProfileStats({
    required this.timelinePlayed,
    required this.timelineWins,
    required this.timelineBest,
    required this.streakPlayed,
    required this.streakBest,
    required this.dailyPlayed,
    required this.dailySolved,
    required this.dailyStreak,
    required this.dailyBestStreak,
    required this.dailyDistribution,
  });

  factory ProfileStats.fromJson(Map<String, dynamic> json) {
    final timeline = json['timeline'] as Map<String, dynamic>;
    final streak = json['streak'] as Map<String, dynamic>;
    final daily = json['daily'] as Map<String, dynamic>;
    return ProfileStats(
      timelinePlayed: timeline['played'] as int,
      timelineWins: timeline['wins'] as int,
      timelineBest: timeline['best_score'] as int,
      streakPlayed: streak['played'] as int,
      streakBest: streak['best'] as int,
      dailyPlayed: daily['played'] as int,
      dailySolved: daily['solved'] as int,
      dailyStreak: daily['current_streak'] as int,
      dailyBestStreak: daily['best_streak'] as int,
      dailyDistribution: {
        for (final MapEntry(:key, :value) in (daily['distribution'] as Map<String, dynamic>).entries) key: value as int,
      },
    );
  }

  final int timelinePlayed;
  final int timelineWins;
  final int timelineBest;
  final int streakPlayed;
  final int streakBest;
  final int dailyPlayed;
  final int dailySolved;
  final int dailyStreak;
  final int dailyBestStreak;

  /// "1" / "2" / "3" = solved on that attempt, "fail" = not solved.
  final Map<String, int> dailyDistribution;
}

final profileProvider = FutureProvider.autoDispose<ProfileStats>((ref) async {
  ref.watch(currentUserIdProvider);
  final data = await ref.watch(apiClientProvider).get('lineup/games/profile/');
  return ProfileStats.fromJson(data as Map<String, dynamic>);
});

final legalDocumentsProvider = FutureProvider.autoDispose<List<LegalDocument>>(
  (ref) => ref.watch(authServiceProvider).legalDocuments(),
);
