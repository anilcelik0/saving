import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';
import '../home/home_data.dart';
import '../timeline/timeline_models.dart';
import 'daily_api.dart';
import 'daily_models.dart';

final dailyApiProvider = Provider<DailyApi>((ref) => DailyApi(ref.watch(apiClientProvider)));

class DailyView {
  const DailyView({required this.puzzle, required this.order, this.last, this.busy = false, this.error});

  final DailyPuzzle puzzle;

  /// The order being arranged on the screen (starts from the server's current order).
  final List<GameCard> order;
  final DailyAttemptResult? last;
  final bool busy;

  /// One-off message for a SnackBar.
  final String? error;

  /// The last attempt's mark for position [i], while that card is still where it was submitted.
  String? markAt(int i) {
    if (puzzle.attempts.isEmpty) return null;
    final a = puzzle.attempts.last;
    return i < a.order.length && a.order[i] == order[i].id ? a.marks[i] : null;
  }
}

/// null = today's puzzle; a number = that past puzzle (Pro archive).
final dailyProvider =
    AsyncNotifierProvider.autoDispose.family<DailyController, DailyView, int?>(DailyController.new);

/// The server checks every attempt (CLAUDE.md rule 8); this keeps the local order and the latest payload.
class DailyController extends AsyncNotifier<DailyView> {
  DailyController(this.number);

  final int? number;

  DailyApi get _api => ref.read(dailyApiProvider);

  @override
  Future<DailyView> build() async {
    final puzzle = await _api.today(number: number);
    return DailyView(puzzle: puzzle, order: puzzle.cards);
  }

  void reorder(int oldIndex, int newIndex) {
    final current = state.value;
    if (current == null || current.busy || !current.puzzle.isPlaying) return;
    final order = [...current.order]; // onReorderItem already adjusts newIndex for the removed item
    order.insert(newIndex, order.removeAt(oldIndex));
    state = AsyncData(DailyView(puzzle: current.puzzle, order: order, last: current.last));
  }

  Future<void> submit() async {
    final current = state.value;
    if (current == null || current.busy || !current.puzzle.isPlaying) return;
    state = AsyncData(DailyView(puzzle: current.puzzle, order: current.order, last: current.last, busy: true));
    try {
      final (result, puzzle) = await _api.attempt(current.puzzle.number, [for (final c in current.order) c.id]);
      state = AsyncData(DailyView(puzzle: puzzle, order: puzzle.cards, last: result));
      ref.invalidate(homeProvider);
    } on ApiException catch (e) {
      // The day changed or the puzzle was finished elsewhere: show the fresh puzzle.
      final reload = e.code == 'daily_expired' || e.code == 'daily_over';
      DailyPuzzle? fresh;
      if (reload) {
        try {
          fresh = await _api.today(number: number);
        } on ApiException {
          fresh = null;
        }
      }
      state = AsyncData(DailyView(
        puzzle: fresh ?? current.puzzle,
        order: fresh?.cards ?? current.order,
        last: fresh == null ? current.last : null,
        error: e.message,
      ));
    }
  }
}
