import '../../core/api_client.dart';
import 'daily_models.dart';

/// Daily puzzle endpoints (/api/v1/lineup/games/daily/...). Free: no energy.
class DailyApi {
  DailyApi(this._api);

  final ApiClient _api;

  /// Today's puzzle, or a past one by [number] (Pro archive).
  Future<DailyPuzzle> today({int? number}) async {
    final data = await _api.get('lineup/games/daily/', query: number == null ? null : {'number': '$number'});
    return DailyPuzzle.fromJson(data as Map<String, dynamic>);
  }

  /// [order] = every card id, lowest value first.
  Future<(DailyAttemptResult, DailyPuzzle)> attempt(int number, List<String> order) async {
    final data = await _api.post('lineup/games/daily/attempts/', data: {'number': number, 'order': order});
    return (
      DailyAttemptResult.fromJson(data['result'] as Map<String, dynamic>),
      DailyPuzzle.fromJson(data['daily'] as Map<String, dynamic>),
    );
  }
}
