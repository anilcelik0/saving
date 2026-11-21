/// Shapes of the `/lineup/games/runs/` payloads. A card's [GameCard.value] is only present after it was played.
class GameCard {
  const GameCard({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.emoji,
    required this.type,
    required this.details,
    this.value,
  });

  factory GameCard.fromJson(Map<String, dynamic> json) => GameCard(
        id: json['id'] as String,
        title: json['title'] as String,
        subtitle: json['subtitle'] as String? ?? '',
        emoji: json['emoji'] as String? ?? '',
        type: json['type'] as String? ?? '',
        details: [for (final d in (json['details'] as List? ?? const [])) d as String],
        value: json['value'] as String?,
      );

  final String id;
  final String title;
  final String subtitle;
  final String emoji;
  final String type;
  final List<String> details;
  final String? value;
}

class RunAttribute {
  const RunAttribute({required this.name, required this.unit, required this.lowerLabel, required this.higherLabel});

  factory RunAttribute.fromJson(Map<String, dynamic> json) => RunAttribute(
        name: json['name'] as String,
        unit: json['unit'] as String? ?? '',
        lowerLabel: json['lower_label'] as String,
        higherLabel: json['higher_label'] as String,
      );

  final String name;
  final String unit;
  final String lowerLabel;
  final String higherLabel;
}

class RunState {
  const RunState({
    required this.id,
    required this.status,
    required this.lives,
    required this.score,
    required this.target,
    required this.attribute,
    required this.line,
    required this.current,
  });

  factory RunState.fromJson(Map<String, dynamic> json) => RunState(
        id: json['id'] as String,
        status: json['status'] as String,
        lives: json['lives'] as int,
        score: json['score'] as int,
        target: json['target'] as int,
        attribute: RunAttribute.fromJson(json['attribute'] as Map<String, dynamic>),
        line: [for (final c in json['line'] as List) GameCard.fromJson(c as Map<String, dynamic>)],
        current: json['current'] == null ? null : GameCard.fromJson(json['current'] as Map<String, dynamic>),
      );

  final String id;

  /// playing | won | lost | finished
  final String status;
  final int lives;
  final int score;
  final int target;
  final RunAttribute attribute;
  final List<GameCard> line;
  final GameCard? current;

  bool get isPlaying => status == 'playing';

  /// Cards to place correctly to win (the start card is already on the line).
  int get goal => target - 1;
}

class MoveResult {
  const MoveResult({required this.correct, required this.validSlots, required this.card});

  factory MoveResult.fromJson(Map<String, dynamic> json) => MoveResult(
        correct: json['correct'] as bool,
        validSlots: [for (final s in json['valid_slots'] as List) s as int],
        card: GameCard.fromJson(json['card'] as Map<String, dynamic>),
      );

  final bool correct;
  final List<int> validSlots;
  final GameCard card;
}
