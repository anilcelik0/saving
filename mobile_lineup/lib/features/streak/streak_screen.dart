import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../home/energy_widgets.dart';
import '../home/home_data.dart';
import '../support/card_report_dialog.dart';
import '../timeline/timeline_models.dart';
import 'streak_controller.dart';
import 'streak_models.dart';

const _higher = 'higher';
const _lower = 'lower';

String _cap(String s) => s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);

/// Streak mode: the open card shows its value; swipe the next card up (higher) or down (lower), or use the buttons.
/// One mistake ends the run. The server judges every guess.
class StreakScreen extends ConsumerWidget {
  const StreakScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.listen(streakProvider, (previous, next) {
      final view = next.value;
      if (view == null) return;
      if (view.error != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(view.error!), behavior: SnackBarBehavior.floating),
        );
      }
      if (view.noEnergy) showNoEnergyDialog(context, ref);
      final last = view.last;
      if (last != null && !identical(last, previous?.value?.last)) {
        last.correct ? HapticFeedback.lightImpact() : HapticFeedback.heavyImpact();
      }
    });

    final async = ref.watch(streakProvider);
    final view = async.value;
    final run = view?.run;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Seri'),
        actions: [
          if (run != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Center(
                child: Text('Seri: ${run.score}  ·  Rekor: ${run.best}', style: Theme.of(context).textTheme.titleSmall),
              ),
            ),
        ],
      ),
      body: SafeArea(
        child: switch (async) {
          AsyncValue(hasError: true) => Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Padding(padding: const EdgeInsets.all(24), child: Text('${async.error}', textAlign: TextAlign.center)),
                  FilledButton(onPressed: () => ref.invalidate(streakProvider), child: const Text('Tekrar dene')),
                ],
              ),
            ),
          _ when view == null => const Center(child: CircularProgressIndicator()),
          _ when run == null => _Intro(busy: view.busy),
          _ => _Board(view: view, run: run),
        },
      ),
    );
  }
}

class _Intro extends ConsumerWidget {
  const _Intro({required this.busy});

  final bool busy;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final best = ref.watch(homeProvider).value?.bestStreak ?? 0;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Daha büyük mü, daha küçük mü?', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            const Text('Açık kartın değerini görürsün. Sıradaki kartı yukarı (daha büyük) ya da aşağı (daha küçük) '
                'kaydır. Her doğru tahmin serini uzatır; ilk hatada tur biter.', textAlign: TextAlign.center),
            if (best > 0) ...[
              const SizedBox(height: 8),
              Text('Rekorun: $best', style: Theme.of(context).textTheme.titleMedium),
            ],
            const SizedBox(height: 24),
            if (busy)
              const CircularProgressIndicator()
            else
              FilledButton(
                onPressed: () => ref.read(streakProvider.notifier).start(),
                child: const Text('Başla · ⚡1'),
              ),
          ],
        ),
      ),
    );
  }
}

class _Board extends ConsumerWidget {
  const _Board({required this.view, required this.run});

  final StreakView view;
  final StreakRun run;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final controller = ref.read(streakProvider.notifier);
    final a = run.attribute;
    final canGuess = run.isPlaying && run.current != null && !view.busy;
    void report(GameCard card) => showCardReportDialog(context, ref, card, screen: 'streak');

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: Text('${a.name}  ·  yukarı: ${a.higherLabel}  ·  aşağı: ${a.lowerLabel}',
              style: theme.textTheme.labelLarge, textAlign: TextAlign.center),
        ),
        if (view.last != null) _ResultBanner(result: view.last!, onReport: () => report(view.last!.card)),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: _OpenCard(card: run.open, onReport: () => report(run.open)),
        ),
        if (run.isPlaying && run.current != null) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: SizedBox(
              width: double.infinity,
              child: FilledButton.tonalIcon(
                onPressed: canGuess ? () => controller.guess(_higher) : null,
                icon: const Icon(Icons.arrow_upward),
                label: Text(_cap(a.higherLabel)),
              ),
            ),
          ),
          _SwipeCard(
            key: ValueKey(run.current!.id),
            card: run.current!,
            enabled: canGuess,
            onGuess: controller.guess,
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: SizedBox(
              width: double.infinity,
              child: FilledButton.tonalIcon(
                onPressed: canGuess ? () => controller.guess(_lower) : null,
                icon: const Icon(Icons.arrow_downward),
                label: Text(_cap(a.lowerLabel)),
              ),
            ),
          ),
          Text(view.busy ? 'Kontrol ediliyor...' : 'Kartı yukarı ya da aşağı kaydır', style: theme.textTheme.bodySmall),
        ] else
          _EndPanel(run: run, busy: view.busy),
        const Divider(),
        Expanded(
          child: ListView(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            children: [
              for (final card in run.history)
                ListTile(
                  dense: true,
                  leading: Text(card.emoji),
                  title: Text(card.title, maxLines: 1, overflow: TextOverflow.ellipsis),
                  trailing: Text(card.value ?? '', style: theme.textTheme.labelLarge),
                  onLongPress: () => report(card),
                ),
            ],
          ),
        ),
      ],
    );
  }
}

/// The reference card: its value is shown big.
class _OpenCard extends StatelessWidget {
  const _OpenCard({required this.card, required this.onReport});

  final GameCard card;
  final VoidCallback onReport;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: EdgeInsets.zero,
      color: theme.colorScheme.secondaryContainer,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onLongPress: onReport,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              if (card.emoji.isNotEmpty) Text(card.emoji, style: const TextStyle(fontSize: 28)),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(card.title, style: theme.textTheme.titleMedium),
                    if (card.subtitle.isNotEmpty) Text(card.subtitle, style: theme.textTheme.bodySmall),
                  ],
                ),
              ),
              Text(card.value ?? '', style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)),
            ],
          ),
        ),
      ),
    );
  }
}

/// The hidden card: drag it up (higher) or down (lower) past a threshold, or flick it.
class _SwipeCard extends StatefulWidget {
  const _SwipeCard({super.key, required this.card, required this.enabled, required this.onGuess});

  final GameCard card;
  final bool enabled;
  final void Function(String guess) onGuess;

  @override
  State<_SwipeCard> createState() => _SwipeCardState();
}

class _SwipeCardState extends State<_SwipeCard> {
  static const _threshold = 50.0;
  static const _flick = 600.0;
  double _dy = 0;

  void _end(DragEndDetails details) {
    final velocity = details.primaryVelocity ?? 0;
    final guess = (_dy <= -_threshold || velocity <= -_flick)
        ? _higher
        : (_dy >= _threshold || velocity >= _flick)
            ? _lower
            : null;
    setState(() => _dy = 0);
    if (guess != null) {
      HapticFeedback.selectionClick();
      widget.onGuess(guess);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final card = widget.card;
    final tint = _dy.abs() >= _threshold ? theme.colorScheme.primaryContainer : null;
    return GestureDetector(
      onVerticalDragUpdate: widget.enabled ? (d) => setState(() => _dy = (_dy + d.delta.dy).clamp(-90.0, 90.0)) : null,
      onVerticalDragEnd: widget.enabled ? _end : null,
      child: Transform.translate(
        offset: Offset(0, _dy),
        child: Card(
          elevation: 3,
          color: tint,
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                if (card.emoji.isNotEmpty) Text(card.emoji, style: const TextStyle(fontSize: 36)),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(card.title, style: theme.textTheme.titleLarge),
                      if (card.subtitle.isNotEmpty) Text(card.subtitle),
                      Text([card.type, ...card.details].join(' · '), style: theme.textTheme.bodySmall),
                    ],
                  ),
                ),
                const Icon(Icons.unfold_more),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ResultBanner extends StatelessWidget {
  const _ResultBanner({required this.result, required this.onReport});

  final GuessResult result;
  final VoidCallback onReport;

  @override
  Widget build(BuildContext context) {
    final ok = result.correct;
    final label = ok ? (result.relation == 'equal' ? 'Eşit, doğru!' : 'Doğru!') : 'Yanlış';
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      padding: const EdgeInsets.only(left: 12),
      decoration: BoxDecoration(
        color: ok ? Colors.green.shade100 : Colors.red.shade100,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(ok ? Icons.check_circle : Icons.cancel, color: ok ? Colors.green.shade800 : Colors.red.shade800),
          const SizedBox(width: 8),
          Expanded(child: Text('$label  ${result.card.title}: ${result.card.value ?? ''}')),
          TextButton(onPressed: onReport, child: const Text('Hata bildir')),
        ],
      ),
    );
  }
}

class _EndPanel extends ConsumerWidget {
  const _EndPanel({required this.run, required this.busy});

  final StreakRun run;
  final bool busy;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final record = run.score > 0 && run.score >= run.best;
    final title = switch (run.status) {
      'finished' => 'Bütün kartları bildin!',
      _ => 'Seri bitti',
    };
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(title, style: theme.textTheme.titleLarge),
          Text(record ? 'Seri: ${run.score} · Yeni rekor!' : 'Seri: ${run.score} · Rekor: ${run.best}'),
          if (run.canContinue) ...[
            const SizedBox(height: 8),
            const OutlinedButton(onPressed: null, child: Text('Reklam izle, devam et (yakında)')),
          ],
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              FilledButton(
                onPressed: busy ? null : () => ref.read(streakProvider.notifier).start(),
                child: const Text('Yeni tur · ⚡1'),
              ),
              const SizedBox(width: 12),
              OutlinedButton(onPressed: () => context.go('/home'), child: const Text('Ana menü')),
            ],
          ),
        ],
      ),
    );
  }
}
