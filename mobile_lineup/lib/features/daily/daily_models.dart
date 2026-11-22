import '../timeline/timeline_models.dart';

/// Per-position marks of an attempt (server values).
const markRight = 'right';
const markNear = 'near';
const markWrong = 'wrong';

const markSquares = {markRight: '🟩', markNear: '🟨', markWrong: '🟥'};

class DailyAttempt {
  const DailyAttempt({required this.order, required this.marks});

  factory DailyAttempt.fromJson(Map<String, dynamic> json) => DailyAttempt(
        order: [for (final id in json['order'] as List) id as String],
        marks: [for (final m in json['marks'] as List) m as String],
      );

  final List<String> order;
  final List<String> marks;

  String get squares => marks.map((m) => markSquares[m] ?? '⬜').join();
}

/// `GET lineup/games/daily/`. Values, [solution] and [share] only arrive once the puzzle is finished.
class DailyPuzzle {
  const DailyPuzzle({
    required this.number,
    required this.status,
    required this.maxAttempts,
    required this.attemptsLeft,
    required this.solvedIn,
    required this.attribute,
    required this.cards,
    required this.attempts,
    required this.nextInSeconds,
    required this.solution,
    required this.share,
    required this.fetchedAt,
  });

  factory DailyPuzzle.fromJson(Map<String, dynamic> json) => DailyPuzzle(
        number: json['number'] as int,
        status: json['status'] as String,
        maxAttempts: json['max_attempts'] as int,
        attemptsLeft: json['attempts_left'] as int,
        solvedIn: json['solved_in'] as int?,
        attribute: RunAttribute.fromJson(json['attribute'] as Map<String, dynamic>),
        cards: [for (final c in json['cards'] as List) GameCard.fromJson(c as Map<String, dynamic>)],
        attempts: [for (final a in json['attempts'] as List) DailyAttempt.fromJson(a as Map<String, dynamic>)],
        nextInSeconds: json['next_in_seconds'] as int,
        solution: [
          for (final c in (json['solution'] as List? ?? const [])) GameCard.fromJson(c as Map<String, dynamic>),
        ],
        share: json['share'] as String?,
        fetchedAt: DateTime.now(),
      );

  final int number;

  /// new | playing | won | lost
  final String status;
  final int maxAttempts;
  final int attemptsLeft;
  final int? solvedIn;
  final RunAttribute attribute;

  /// In the current order: the last attempt's, else as dealt.
  final List<GameCard> cards;
  final List<DailyAttempt> attempts;

  /// Until the next puzzle (Europe/Istanbul midnight), counted down locally from [fetchedAt].
  final int nextInSeconds;
  final List<GameCard> solution;
  final String? share;
  final DateTime fetchedAt;

  bool get isPlaying => status == 'new' || status == 'playing';
}

class DailyAttemptResult {
  const DailyAttemptResult({required this.marks, required this.solved, required this.attempt});

  factory DailyAttemptResult.fromJson(Map<String, dynamic> json) => DailyAttemptResult(
        marks: [for (final m in json['marks'] as List) m as String],
        solved: json['solved'] as bool,
        attempt: json['attempt'] as int,
      );

  final List<String> marks;
  final bool solved;
  final int attempt;
}
