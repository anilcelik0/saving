import '../timeline/timeline_models.dart';

/// A Streak run (`mode=streak`). [open] carries its value; [current] never does until it is guessed.
class StreakRun {
  const StreakRun({
    required this.id,
    required this.status,
    required this.lives,
    required this.score,
    required this.best,
    required this.canContinue,
    required this.attribute,
    required this.open,
    required this.current,
    required this.history,
  });

  factory StreakRun.fromJson(Map<String, dynamic> json) => StreakRun(
        id: json['id'] as String,
        status: json['status'] as String,
        lives: json['lives'] as int,
        score: json['score'] as int,
        best: json['best'] as int,
        canContinue: json['can_continue'] as bool,
        attribute: RunAttribute.fromJson(json['attribute'] as Map<String, dynamic>),
        open: GameCard.fromJson(json['open'] as Map<String, dynamic>),
        current: json['current'] == null ? null : GameCard.fromJson(json['current'] as Map<String, dynamic>),
        history: [for (final c in json['history'] as List) GameCard.fromJson(c as Map<String, dynamic>)],
      );

  final String id;

  /// playing | lost | finished | abandoned
  final String status;
  final int lives;
  final int score;
  final int best;

  /// A continue after the loss is possible (rewarded ad / Pro, Phase 5).
  final bool canContinue;
  final RunAttribute attribute;
  final GameCard open;
  final GameCard? current;

  /// Revealed cards before [open], newest first.
  final List<GameCard> history;

  bool get isPlaying => status == 'playing';
}

class GuessResult {
  const GuessResult({required this.correct, required this.guess, required this.relation, required this.card});

  factory GuessResult.fromJson(Map<String, dynamic> json) => GuessResult(
        correct: json['correct'] as bool,
        guess: json['guess'] as String,
        relation: json['relation'] as String,
        card: GameCard.fromJson(json['card'] as Map<String, dynamic>),
      );

  final bool correct;

  /// higher | lower
  final String guess;

  /// higher | lower | equal (revealed card vs the previous open card)
  final String relation;
  final GameCard card;
}
