import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';
import '../home/home_data.dart';
import 'streak_api.dart';
import 'streak_models.dart';

final streakApiProvider = Provider<StreakApi>((ref) => StreakApi(ref.watch(apiClientProvider)));

class StreakView {
  const StreakView({this.run, this.last, this.busy = false, this.error, this.noEnergy = false});

  final StreakRun? run;
  final GuessResult? last;
  final bool busy;

  /// One-off message for a SnackBar.
  final String? error;

  /// One-off: the start was refused for lack of energy.
  final bool noEnergy;
}

/// null = the normal run being played (resume); a run id = that run (a challenge run).
final streakProvider =
    AsyncNotifierProvider.autoDispose.family<StreakController, StreakView, String?>(StreakController.new);

/// The server decides every guess (CLAUDE.md rule 8); this only sends them and keeps the latest payload.
class StreakController extends AsyncNotifier<StreakView> {
  StreakController(this.runId);

  final String? runId;

  StreakApi get _api => ref.read(streakApiProvider);

  @override
  Future<StreakView> build() async =>
      StreakView(run: runId == null ? await _api.playing() : await _api.get(runId!));

  Future<void> start() async {
    final current = state.value ?? const StreakView();
    if (current.busy) return;
    state = AsyncData(StreakView(run: current.run, busy: true));
    try {
      state = AsyncData(StreakView(run: await _api.start()));
      ref.invalidate(homeProvider);
    } on ApiException catch (e) {
      state = AsyncData(StreakView(
        run: current.run,
        last: current.last,
        error: e.code == 'no_energy' ? null : e.message,
        noEnergy: e.code == 'no_energy',
      ));
    }
  }

  /// After a continue (rewarded ad / Pro) the server resumed the run: show it again.
  Future<void> reload() async {
    final run = state.value?.run;
    if (run == null) return;
    state = AsyncData(StreakView(run: await _api.get(run.id)));
  }

  Future<void> guess(String guess) async {
    final current = state.value;
    final run = current?.run;
    if (current == null || run == null || !run.isPlaying || current.busy) return;
    state = AsyncData(StreakView(run: run, last: current.last, busy: true));
    try {
      final (result, next) = await _api.guess(run.id, guess);
      state = AsyncData(StreakView(run: next, last: result));
      if (!next.isPlaying) ref.invalidate(homeProvider);
    } on ApiException catch (e) {
      StreakRun? fresh;
      try {
        fresh = runId == null ? await _api.playing() : await _api.get(runId!);
      } on ApiException {
        fresh = null;
      }
      state = AsyncData(StreakView(run: fresh ?? run, last: current.last, error: e.message));
    }
  }
}
