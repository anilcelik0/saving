import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';
import '../home/home_data.dart';
import 'timeline_api.dart';
import 'timeline_models.dart';

final timelineApiProvider = Provider<TimelineApi>((ref) => TimelineApi(ref.watch(apiClientProvider)));

/// Screen state: no run yet (difficulty picker), or a run with the last move's result.
class TimelineView {
  const TimelineView({this.run, this.last, this.busy = false, this.error, this.noEnergy = false});

  final RunState? run;
  final MoveResult? last;

  /// A request is in flight: no second move meanwhile.
  final bool busy;

  /// One-off message for a SnackBar (cleared on the next change).
  final String? error;

  /// One-off: the start was refused for lack of energy (the screen shows the dialog).
  final bool noEnergy;

  TimelineView copyWith(
          {RunState? run, MoveResult? last, bool? busy, String? error, bool noEnergy = false, bool clearLast = false}) =>
      TimelineView(
        run: run ?? this.run,
        last: clearLast ? null : (last ?? this.last),
        busy: busy ?? this.busy,
        error: error,
        noEnergy: noEnergy,
      );
}

final timelineProvider =
    AsyncNotifierProvider.autoDispose<TimelineController, TimelineView>(TimelineController.new);

/// The server decides everything (CLAUDE.md rule 8); this only sends moves and keeps the latest payload.
class TimelineController extends AsyncNotifier<TimelineView> {
  TimelineApi get _api => ref.read(timelineApiProvider);

  @override
  Future<TimelineView> build() async => TimelineView(run: await _api.playing());

  Future<void> start(String difficulty) async {
    final current = state.value ?? const TimelineView();
    state = AsyncData(current.copyWith(busy: true, clearLast: true));
    try {
      state = AsyncData(TimelineView(run: await _api.start(difficulty: difficulty)));
      ref.invalidate(homeProvider);
    } on ApiException catch (e) {
      state = AsyncData(e.code == 'no_energy'
          ? current.copyWith(busy: false, noEnergy: true)
          : current.copyWith(busy: false, error: e.message));
    }
  }

  /// Back to the difficulty picker after a finished run.
  void newRun() => state = const AsyncData(TimelineView());

  Future<void> place(int slot) async {
    final current = state.value;
    final run = current?.run;
    if (current == null || run == null || !run.isPlaying || current.busy) return;
    state = AsyncData(current.copyWith(busy: true));
    try {
      final (result, next) = await _api.move(run.id, slot);
      state = AsyncData(TimelineView(run: next, last: result));
      if (!next.isPlaying) ref.invalidate(homeProvider);
    } on ApiException catch (e) {
      // e.g. the run ended meanwhile: reload what the server has
      RunState? fresh;
      try {
        fresh = await _api.playing();
      } on ApiException {
        fresh = null;
      }
      state = AsyncData(TimelineView(run: fresh ?? run, last: current.last, error: e.message));
    }
  }
}
