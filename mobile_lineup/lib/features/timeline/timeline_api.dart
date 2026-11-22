import '../../core/api_client.dart';
import 'timeline_models.dart';

/// `lineup_games` endpoints (/api/v1/lineup/games/runs/...).
class TimelineApi {
  TimelineApi(this._api);

  final ApiClient _api;

  /// The run being played, if any (to resume after leaving the screen).
  Future<RunState?> playing() async {
    final data = await _api.get('lineup/games/runs/', query: {'mode': 'timeline'});
    final playing = data['playing'];
    return playing == null ? null : RunState.fromJson(playing as Map<String, dynamic>);
  }

  Future<RunState> get(String runId) async =>
      RunState.fromJson(await _api.get('lineup/games/runs/$runId/') as Map<String, dynamic>);

  Future<RunState> start({required String difficulty}) async {
    final data = await _api.post('lineup/games/runs/', data: {'mode': 'timeline', 'difficulty': difficulty});
    return RunState.fromJson(data as Map<String, dynamic>);
  }

  /// [slot] = gap index (0 = above the first card).
  Future<(MoveResult, RunState)> move(String runId, int slot) async {
    final data = await _api.post('lineup/games/runs/$runId/moves/', data: {'slot': slot});
    return (
      MoveResult.fromJson(data['result'] as Map<String, dynamic>),
      RunState.fromJson(data['run'] as Map<String, dynamic>),
    );
  }
}
