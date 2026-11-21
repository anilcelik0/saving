import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';

/// Energy as the server computed it; the seconds count down locally from [fetchedAt].
class EnergyInfo {
  const EnergyInfo({
    required this.current,
    required this.max,
    required this.cost,
    required this.unlimited,
    required this.unlimitedSeconds,
    required this.nextInSeconds,
    required this.fullInSeconds,
    required this.fetchedAt,
  });

  factory EnergyInfo.fromJson(Map<String, dynamic> json) => EnergyInfo(
        current: json['current'] as int,
        max: json['max'] as int,
        cost: json['cost'] as int,
        unlimited: json['unlimited'] as bool,
        unlimitedSeconds: json['unlimited_seconds'] as int?,
        nextInSeconds: json['next_in_seconds'] as int?,
        fullInSeconds: json['full_in_seconds'] as int?,
        fetchedAt: DateTime.now(),
      );

  final int current;
  final int max;
  final int cost;

  /// New players' first days (later also Pro): starts cost nothing.
  final bool unlimited;
  final int? unlimitedSeconds;

  /// null when full.
  final int? nextInSeconds;
  final int? fullInSeconds;
  final DateTime fetchedAt;

  bool get canStart => unlimited || current >= cost;

  /// Seconds left from [total] (as sent by the server) at [now].
  int left(int total, DateTime now) {
    final passed = now.difference(fetchedAt).inSeconds;
    return total - passed < 0 ? 0 : total - passed;
  }
}

class PlayingRun {
  const PlayingRun({required this.id, required this.score});

  final String id;
  final int score;
}

/// `GET lineup/games/home/`: energy, runs to resume, records.
class HomeInfo {
  const HomeInfo({required this.energy, required this.playing, required this.bestStreak, required this.timelineWins});

  factory HomeInfo.fromJson(Map<String, dynamic> json) {
    final playing = json['playing'] as Map<String, dynamic>;
    return HomeInfo(
      energy: EnergyInfo.fromJson(json['energy'] as Map<String, dynamic>),
      playing: {
        for (final MapEntry(:key, :value) in playing.entries)
          if (value is Map) key: PlayingRun(id: value['id'] as String, score: value['score'] as int),
      },
      bestStreak: json['best_streak'] as int,
      timelineWins: json['timeline_wins'] as int,
    );
  }

  final EnergyInfo energy;

  /// mode -> run being played
  final Map<String, PlayingRun> playing;
  final int bestStreak;
  final int timelineWins;
}

/// Refreshed by the game controllers after a start (energy spent) and when a run ends.
final homeProvider = FutureProvider.autoDispose<HomeInfo>((ref) async {
  final data = await ref.watch(apiClientProvider).get('lineup/games/home/');
  return HomeInfo.fromJson(data as Map<String, dynamic>);
});
