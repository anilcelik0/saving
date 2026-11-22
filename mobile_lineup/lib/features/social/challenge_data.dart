import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';
import '../session/session_controller.dart';

/// One player's result on a challenge deck.
class ChallengeEntry {
  const ChallengeEntry({required this.username, required this.runId, required this.score, required this.status,
      required this.finished, required this.outcome});

  factory ChallengeEntry.fromJson(Map<String, dynamic> json) => ChallengeEntry(
        username: json['username'] as String,
        runId: json['run_id'] as String,
        score: json['score'] as int,
        status: json['status'] as String,
        finished: json['finished'] as bool,
        outcome: json['outcome'] as String?,
      );

  final String username;
  final String runId;
  final int score;
  final String status;
  final bool finished;

  /// win | lose | tie (against the creator), null while playing.
  final String? outcome;
}

/// `GET lineup/social/challenges/<code>/`: never the cards, only who played and the scores.
class Challenge {
  const Challenge({
    required this.code,
    required this.link,
    required this.mode,
    required this.modeLabel,
    required this.attribute,
    required this.creator,
    required this.creatorScore,
    required this.expiresAt,
    required this.expired,
    required this.isCreator,
    required this.myEntry,
    required this.entries,
    required this.shareText,
  });

  factory Challenge.fromJson(Map<String, dynamic> json) => Challenge(
        code: json['code'] as String,
        link: json['link'] as String,
        mode: json['mode'] as String,
        modeLabel: json['mode_label'] as String,
        attribute: (json['attribute'] as Map<String, dynamic>)['name'] as String,
        creator: json['creator'] as String,
        creatorScore: json['creator_score'] as int,
        expiresAt: DateTime.parse(json['expires_at'] as String).toLocal(),
        expired: json['expired'] as bool,
        isCreator: json['is_creator'] as bool,
        myEntry: json['my_entry'] == null ? null : ChallengeEntry.fromJson(json['my_entry'] as Map<String, dynamic>),
        entries: [for (final e in json['entries'] as List) ChallengeEntry.fromJson(e as Map<String, dynamic>)],
        shareText: json['share_text'] as String,
      );

  final String code;
  final String link;

  /// timeline | streak
  final String mode;
  final String modeLabel;
  final String attribute;
  final String creator;
  final int creatorScore;
  final DateTime expiresAt;
  final bool expired;
  final bool isCreator;
  final ChallengeEntry? myEntry;
  final List<ChallengeEntry> entries;
  final String shareText;

  /// Route of the game screen for a challenge run.
  String playRoute(String runId) => '/home/$mode?run=$runId&challenge=$code';
}

/// Row of the challenge lists.
class ChallengeRow {
  const ChallengeRow({required this.code, required this.modeLabel, required this.attribute, required this.creator,
      required this.creatorScore, required this.expired, this.entries, this.myEntry});

  factory ChallengeRow.fromJson(Map<String, dynamic> json) => ChallengeRow(
        code: json['code'] as String,
        modeLabel: json['mode_label'] as String,
        attribute: json['attribute'] as String,
        creator: json['creator'] as String,
        creatorScore: json['creator_score'] as int,
        expired: json['expired'] as bool,
        entries: json['entries'] as int?,
        myEntry: json['my_entry'] == null ? null : ChallengeEntry.fromJson(json['my_entry'] as Map<String, dynamic>),
      );

  final String code;
  final String modeLabel;
  final String attribute;
  final String creator;
  final int creatorScore;
  final bool expired;

  /// Sent: how many played it.
  final int? entries;

  /// Played: my result.
  final ChallengeEntry? myEntry;
}

class ChallengeLists {
  const ChallengeLists({required this.incoming, required this.sent, required this.played});

  factory ChallengeLists.fromJson(Map<String, dynamic> json) {
    List<ChallengeRow> rows(String key) =>
        [for (final r in json[key] as List) ChallengeRow.fromJson(r as Map<String, dynamic>)];
    return ChallengeLists(incoming: rows('incoming'), sent: rows('sent'), played: rows('played'));
  }

  final List<ChallengeRow> incoming;
  final List<ChallengeRow> sent;
  final List<ChallengeRow> played;
}

final socialApiProvider = Provider<SocialApi>((ref) => SocialApi(ref.watch(apiClientProvider)));

/// `/api/v1/lineup/social/challenges/...`
class SocialApi {
  SocialApi(this._api);

  final ApiClient _api;

  Future<ChallengeLists> lists() async =>
      ChallengeLists.fromJson(await _api.get('lineup/social/challenges/') as Map<String, dynamic>);

  /// From a finished run; the same run always gives the same challenge.
  Future<Challenge> create(String runId) async =>
      Challenge.fromJson(await _api.post('lineup/social/challenges/', data: {'run': runId}) as Map<String, dynamic>);

  Future<Challenge> get(String code) async =>
      Challenge.fromJson(await _api.get('lineup/social/challenges/$code/') as Map<String, dynamic>);

  /// Free; returns the run id to play (accepting again returns the same run).
  Future<String> accept(String code) async {
    final data = await _api.post('lineup/social/challenges/$code/accept/');
    return (data['run'] as Map<String, dynamic>)['id'] as String;
  }

  Future<void> send(String code, String username) =>
      _api.post('lineup/social/challenges/$code/send/', data: {'username': username});
}

final challengeListsProvider = FutureProvider.autoDispose<ChallengeLists>((ref) {
  ref.watch(currentUserIdProvider);
  return ref.watch(socialApiProvider).lists();
});

final challengeProvider = FutureProvider.autoDispose.family<Challenge, String>((ref, code) {
  ref.watch(currentUserIdProvider);
  return ref.watch(socialApiProvider).get(code);
});
