import '../../core/api_client.dart';
import 'streak_models.dart';

/// Streak runs on the shared runs endpoints (/api/v1/lineup/games/runs/...).
class StreakApi {
  StreakApi(this._api);

  final ApiClient _api;

  Future<StreakRun?> playing() async {
    final data = await _api.get('lineup/games/runs/', query: {'mode': 'streak'});
    final playing = data['playing'];
    return playing == null ? null : StreakRun.fromJson(playing as Map<String, dynamic>);
  }

  Future<StreakRun> get(String runId) async =>
      StreakRun.fromJson(await _api.get('lineup/games/runs/$runId/') as Map<String, dynamic>);

  Future<StreakRun> start() async {
    final data = await _api.post('lineup/games/runs/', data: {'mode': 'streak'});
    return StreakRun.fromJson(data as Map<String, dynamic>);
  }

  /// [guess] = `higher` or `lower`.
  Future<(GuessResult, StreakRun)> guess(String runId, String guess) async {
    final data = await _api.post('lineup/games/runs/$runId/moves/', data: {'guess': guess});
    return (
      GuessResult.fromJson(data['result'] as Map<String, dynamic>),
      StreakRun.fromJson(data['run'] as Map<String, dynamic>),
    );
  }
}
