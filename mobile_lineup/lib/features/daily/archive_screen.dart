import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';
import '../session/session_controller.dart';

class ArchiveEntry {
  const ArchiveEntry({required this.number, required this.date, required this.attribute, required this.status,
      required this.solvedIn});

  factory ArchiveEntry.fromJson(Map<String, dynamic> json) => ArchiveEntry(
        number: json['number'] as int,
        date: DateTime.parse(json['date'] as String),
        attribute: json['attribute'] as String,
        status: json['status'] as String,
        solvedIn: json['solved_in'] as int?,
      );

  final int number;
  final DateTime date;
  final String attribute;

  /// new | playing | won | lost
  final String status;
  final int? solvedIn;
}

/// `GET daily/archive/` (Pro). A non-Pro user gets ApiException code `pro_required`.
final archiveProvider = FutureProvider.autoDispose<List<ArchiveEntry>>((ref) async {
  ref.watch(currentUserIdProvider);
  final data = await ref.watch(apiClientProvider).get('lineup/games/daily/archive/');
  return [for (final p in data['puzzles'] as List) ArchiveEntry.fromJson(p as Map<String, dynamic>)];
});

/// Past daily puzzles (Pro). Solving one later does not count for the daily streak.
class ArchiveScreen extends ConsumerWidget {
  const ArchiveScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final archive = ref.watch(archiveProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Geçmiş bulmacalar')),
      body: switch (archive) {
        AsyncValue(:final error?) when error is ApiException && error.code == 'pro_required' => Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.workspace_premium, size: 48),
                  const SizedBox(height: 12),
                  const Text('Geçmiş günlerin bulmacalarını çözmek Pro üyelere özel.', textAlign: TextAlign.center),
                  const SizedBox(height: 16),
                  FilledButton(onPressed: () => context.push('/home/pro'), child: const Text("Pro'yu incele")),
                ],
              ),
            ),
          ),
        AsyncValue(:final error?) => Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Padding(padding: const EdgeInsets.all(24), child: Text('$error', textAlign: TextAlign.center)),
                FilledButton(onPressed: () => ref.invalidate(archiveProvider), child: const Text('Tekrar dene')),
              ],
            ),
          ),
        AsyncValue(:final value?) when value.isEmpty => const Center(child: Text('Henüz geçmiş bulmaca yok.')),
        AsyncValue(:final value?) => RefreshIndicator(
            onRefresh: () => ref.refresh(archiveProvider.future),
            child: ListView(
              children: [
                for (final p in value)
                  ListTile(
                    leading: Text(switch (p.status) {
                      'won' => '🟩',
                      'lost' => '🟥',
                      'playing' => '🟨',
                      _ => '⬜',
                    }, style: const TextStyle(fontSize: 22)),
                    title: Text('#${p.number} · ${p.attribute}'),
                    subtitle: Text('${p.date.day}.${p.date.month}.${p.date.year}'
                        '${p.solvedIn != null ? ' · ${p.solvedIn}. denemede çözüldü' : ''}'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () async {
                      await context.push('/home/archive/${p.number}');
                      ref.invalidate(archiveProvider);
                    },
                  ),
              ],
            ),
          ),
        _ => const Center(child: CircularProgressIndicator()),
      },
    );
  }
}
