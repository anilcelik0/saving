import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';
import 'package:share_plus/share_plus.dart';

import '../home/energy_widgets.dart';
import '../support/card_report_dialog.dart';
import '../timeline/timeline_models.dart';
import 'daily_controller.dart';
import 'daily_models.dart';

/// Daily puzzle: the same cards for everyone today. Drag them into order (lowest value on top) and check; each
/// position turns green (right), yellow (one place off) or red. Three attempts, free. The server checks every attempt.
class DailyScreen extends ConsumerWidget {
  const DailyScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.listen(dailyProvider, (previous, next) {
      final view = next.value;
      if (view == null) return;
      if (view.error != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(view.error!), behavior: SnackBarBehavior.floating),
        );
      }
      final last = view.last;
      if (last != null && !identical(last, previous?.value?.last)) {
        last.solved ? HapticFeedback.lightImpact() : HapticFeedback.heavyImpact();
      }
    });

    final async = ref.watch(dailyProvider);
    final view = async.value;
    return Scaffold(
      appBar: AppBar(title: Text(view == null ? 'Günlük Bulmaca' : 'Günlük Bulmaca #${view.puzzle.number}')),
      body: SafeArea(
        child: switch (async) {
          AsyncValue(hasError: true) => Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Padding(padding: const EdgeInsets.all(24), child: Text('${async.error}', textAlign: TextAlign.center)),
                  FilledButton(onPressed: () => ref.invalidate(dailyProvider), child: const Text('Tekrar dene')),
                ],
              ),
            ),
          _ when view == null => const Center(child: CircularProgressIndicator()),
          _ when view.puzzle.isPlaying => _Board(view: view),
          _ => _Result(view: view),
        },
      ),
    );
  }
}

Color? _markColor(String? mark) => switch (mark) {
      markRight => Colors.green.shade100,
      markNear => Colors.amber.shade100,
      markWrong => Colors.red.shade100,
      _ => null,
    };

class _Board extends ConsumerWidget {
  const _Board({required this.view});

  final DailyView view;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final puzzle = view.puzzle;
    final a = puzzle.attribute;
    final controller = ref.read(dailyProvider.notifier);
    final attemptNo = puzzle.attempts.length + 1;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: Column(
            children: [
              Text(a.name, style: theme.textTheme.titleMedium),
              Text('Üstte: ${a.lowerLabel}  ·  altta: ${a.higherLabel}', style: theme.textTheme.labelLarge),
              const SizedBox(height: 4),
              Text(
                puzzle.attempts.isEmpty
                    ? 'Kartları sürükleyerek sırala. ${puzzle.maxAttempts} deneme hakkın var.'
                    : 'Kalan deneme: ${puzzle.attemptsLeft}/${puzzle.maxAttempts}',
                style: theme.textTheme.bodySmall,
              ),
              for (final (i, attempt) in puzzle.attempts.indexed)
                Text('${i + 1}. deneme  ${attempt.squares}', style: theme.textTheme.bodyMedium),
            ],
          ),
        ),
        Expanded(
          child: ReorderableListView.builder(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            buildDefaultDragHandles: false,
            itemCount: view.order.length,
            onReorderItem: controller.reorder,
            itemBuilder: (context, i) {
              final card = view.order[i];
              return ReorderableDelayedDragStartListener(
                key: ValueKey(card.id),
                index: i,
                enabled: !view.busy,
                child: Card(
                  color: _markColor(view.markAt(i)),
                  child: ListTile(
                    leading: Text(card.emoji.isEmpty ? '${i + 1}' : card.emoji, style: const TextStyle(fontSize: 24)),
                    title: Text(card.title),
                    subtitle: Text([if (card.subtitle.isNotEmpty) card.subtitle, card.type, ...card.details].join(' · '),
                        maxLines: 2, overflow: TextOverflow.ellipsis),
                    trailing: ReorderableDragStartListener(
                      index: i,
                      enabled: !view.busy,
                      child: const Padding(padding: EdgeInsets.all(8), child: Icon(Icons.drag_handle)),
                    ),
                  ),
                ),
              );
            },
          ),
        ),
        Text('🟩 doğru yer  ·  🟨 bir yer yanında  ·  🟥 daha uzakta', style: theme.textTheme.bodySmall),
        Padding(
          padding: const EdgeInsets.all(16),
          child: SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: view.busy ? null : controller.submit,
              icon: view.busy
                  ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.check),
              label: Text('Kontrol et ($attemptNo. deneme)'),
            ),
          ),
        ),
      ],
    );
  }
}

class _Result extends ConsumerWidget {
  const _Result({required this.view});

  final DailyView view;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final puzzle = view.puzzle;
    final a = puzzle.attribute;
    final solved = puzzle.status == 'won';
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(solved ? 'Çözdün! (${puzzle.solvedIn}. deneme)' : 'Bu sefer olmadı',
            style: theme.textTheme.headlineSmall, textAlign: TextAlign.center),
        const SizedBox(height: 8),
        for (final (i, attempt) in puzzle.attempts.indexed)
          Text('${i + 1}. deneme  ${attempt.squares}', textAlign: TextAlign.center, style: theme.textTheme.titleMedium),
        const SizedBox(height: 12),
        if (puzzle.share != null)
          FilledButton.icon(
            onPressed: () => SharePlus.instance.share(ShareParams(text: puzzle.share!)),
            icon: const Icon(Icons.share),
            label: const Text('Sonucu paylaş'),
          ),
        const SizedBox(height: 4),
        _NextPuzzle(puzzle: puzzle, onReady: () => ref.invalidate(dailyProvider)),
        const Divider(height: 32),
        Text('Doğru sıra · ${a.name} (üstte ${a.lowerLabel})', style: theme.textTheme.titleSmall),
        for (final card in puzzle.solution) _SolutionTile(card: card),
        const SizedBox(height: 8),
        Text('Bir değer yanlışsa karta uzun bas.', style: theme.textTheme.bodySmall, textAlign: TextAlign.center),
      ],
    );
  }
}

class _SolutionTile extends ConsumerWidget {
  const _SolutionTile({required this.card});

  final GameCard card;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListTile(
      dense: true,
      leading: Text(card.emoji, style: const TextStyle(fontSize: 20)),
      title: Text(card.title, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: card.subtitle.isEmpty ? null : Text(card.subtitle, maxLines: 1, overflow: TextOverflow.ellipsis),
      trailing: Text(card.value ?? '', style: Theme.of(context).textTheme.labelLarge),
      onLongPress: () => showCardReportDialog(context, ref, card, screen: 'daily'),
    );
  }
}

/// "Yeni bulmaca 5 sa 12 dk sonra"; reloads the screen when the day changes.
class _NextPuzzle extends StatefulWidget {
  const _NextPuzzle({required this.puzzle, required this.onReady});

  final DailyPuzzle puzzle;
  final VoidCallback onReady;

  @override
  State<_NextPuzzle> createState() => _NextPuzzleState();
}

class _NextPuzzleState extends State<_NextPuzzle> {
  Timer? _timer;
  bool _fired = false;

  int get _left {
    final passed = DateTime.now().difference(widget.puzzle.fetchedAt).inSeconds;
    final left = widget.puzzle.nextInSeconds - passed;
    return left < 0 ? 0 : left;
  }

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (_left == 0 && !_fired) {
        _fired = true;
        widget.onReady();
      }
      setState(() {});
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      Text('Yeni bulmaca ${formatWait(_left)} sonra', textAlign: TextAlign.center);
}
