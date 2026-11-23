import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/theme.dart';
import '../home/energy_widgets.dart';
import '../home/home_data.dart';
import '../support/card_report_dialog.dart';
import '../timeline/timeline_models.dart';
import 'daily_controller.dart';
import 'daily_models.dart';

/// Daily puzzle: the same cards for everyone today. Drag them into order (lowest value on top) and check; each
/// position turns green (right), yellow (one place off) or red. Five attempts (engine.daily.ATTEMPTS), free. The server checks every attempt.
/// Layout: Phase 8 design "Günlük · Gece" (attempt grid + value axis) on the light theme.
class DailyScreen extends ConsumerWidget {
  const DailyScreen({super.key, this.number});

  /// null = today's puzzle; else a past one (Pro archive).
  final int? number;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final provider = dailyProvider(number);
    ref.listen(provider, (previous, next) {
      final view = next.value;
      if (view == null) return;
      if (view.error != null) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(view.error!)));
      }
      final last = view.last;
      if (last != null && !identical(last, previous?.value?.last)) {
        last.solved ? HapticFeedback.lightImpact() : HapticFeedback.heavyImpact();
      }
    });

    final async = ref.watch(provider);
    final view = async.value;
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            _Header(view: view, number: number),
            Expanded(
              child: switch (async) {
                AsyncValue(hasError: true) => Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Padding(
                          padding: const EdgeInsets.all(24),
                          child: Text('${async.error}', textAlign: TextAlign.center),
                        ),
                        FilledButton(onPressed: () => ref.invalidate(provider), child: const Text('Tekrar dene')),
                      ],
                    ),
                  ),
                _ when view == null => const Center(child: CircularProgressIndicator()),
                _ when view.puzzle.isPlaying => _Board(view: view, number: number),
                _ => _Result(view: view, number: number),
              },
            ),
          ],
        ),
      ),
    );
  }
}

/// Back · "#42 · Dağlar" · daily streak · archive.
class _Header extends ConsumerWidget {
  const _Header({required this.view, required this.number});

  final DailyView? view;
  final int? number;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final puzzle = view?.puzzle;
    final streak = number == null ? ref.watch(homeProvider).value?.daily?.streak ?? 0 : 0;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 12),
      child: Row(
        children: [
          CircleIconButton(
            icon: Icons.chevron_left,
            tooltip: 'Geri',
            onPressed: () => context.canPop() ? context.pop() : context.go('/home'),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: puzzle == null
                ? Text('Günlük bulmaca', style: display(20))
                : Text.rich(
                    TextSpan(children: [
                      TextSpan(text: puzzle.archived ? 'Arşiv #${puzzle.number} · ' : '#${puzzle.number} · '),
                      TextSpan(text: puzzle.attribute.name, style: const TextStyle(color: LU.primary)),
                    ]),
                    style: display(20),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
          ),
          if (streak > 0)
            Padding(
              padding: const EdgeInsets.only(left: 8),
              child: Text('$streak gün seri',
                  style: const TextStyle(color: LU.accentText, fontWeight: FontWeight.w600, fontSize: 13)),
            ),
          if (number == null) ...[
            const SizedBox(width: 8),
            CircleIconButton(
              icon: Icons.history,
              tooltip: 'Geçmiş bulmacalar',
              onPressed: () => context.push('/home/archive'),
            ),
          ],
        ],
      ),
    );
  }
}

/// One mark square: color plus an icon, so the marks never rely on color alone.
class MarkSquare extends StatelessWidget {
  const MarkSquare({super.key, required this.mark, this.size = 26, this.current = false});

  /// right | near | wrong; null = an empty slot.
  final String? mark;
  final double size;

  /// The row being played now (outlined).
  final bool current;

  @override
  Widget build(BuildContext context) {
    final (color, icon, iconColor) = switch (mark) {
      markRight => (LU.right, Icons.check_rounded, Colors.white),
      markNear => (LU.near, Icons.swap_vert_rounded, LU.ink),
      markWrong => (LU.wrong, Icons.close_rounded, Colors.white),
      _ => (current ? LU.surface : LU.empty, null, null),
    };
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(size * 0.27),
        border: current ? Border.all(color: LU.primary, width: 1.5) : null,
      ),
      child: icon == null ? null : Icon(icon, size: size * 0.62, color: iconColor),
    );
  }
}

/// Every attempt as a row of squares; while playing the next row is outlined and the rest stay empty.
class _AttemptGrid extends StatelessWidget {
  const _AttemptGrid({required this.puzzle, this.size = 26});

  final DailyPuzzle puzzle;
  final double size;

  @override
  Widget build(BuildContext context) {
    final columns = puzzle.cards.length;
    final rows = puzzle.isPlaying ? puzzle.maxAttempts : puzzle.attempts.length;
    final gap = size * 0.2;
    final summary = [
      for (final (i, a) in puzzle.attempts.indexed)
        '${i + 1}. deneme: ${a.marks.where((m) => m == markRight).length} doğru, '
            '${a.marks.where((m) => m == markNear).length} yakın, '
            '${a.marks.where((m) => m == markWrong).length} uzak',
    ].join('. ');
    return Semantics(
      label: summary.isEmpty ? 'Henüz deneme yok' : summary,
      excludeSemantics: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var r = 0; r < rows; r++)
            Padding(
              padding: EdgeInsets.only(bottom: r == rows - 1 ? 0 : gap),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (var c = 0; c < columns; c++)
                    Padding(
                      padding: EdgeInsets.only(right: c == columns - 1 ? 0 : gap),
                      child: MarkSquare(
                        size: size,
                        mark: r < puzzle.attempts.length && c < puzzle.attempts[r].marks.length
                            ? puzzle.attempts[r].marks[c]
                            : null,
                        current: r == puzzle.attempts.length,
                      ),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _Board extends ConsumerWidget {
  const _Board({required this.view, required this.number});

  final DailyView view;
  final int? number;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final puzzle = view.puzzle;
    final a = puzzle.attribute;
    final controller = ref.read(dailyProvider(number).notifier);
    final attemptNo = puzzle.attempts.length + 1;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            decoration: BoxDecoration(
              color: LU.surface,
              borderRadius: BorderRadius.circular(22),
              boxShadow: LU.shadow,
            ),
            child: Row(
              children: [
                _AttemptGrid(puzzle: puzzle, size: 22),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text.rich(
                        TextSpan(children: [
                          TextSpan(text: '$attemptNo'),
                          TextSpan(text: '/${puzzle.maxAttempts}', style: display(16, color: LU.muted)),
                        ]),
                        style: display(28),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        puzzle.attempts.isEmpty
                            ? 'deneme. Uzun bas, sürükle, sonra kontrol et.'
                            : 'deneme. Yeşil doğru yer, sarı bir yer kaymış, kırmızı uzak.',
                        style: const TextStyle(fontSize: 12, color: LU.muted, height: 1.35),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _Axis(lower: a.lowerLabel, higher: a.higherLabel),
                const SizedBox(width: 10),
                Expanded(
                  child: ReorderableListView.builder(
                    buildDefaultDragHandles: false,
                    itemCount: view.order.length,
                    onReorderItem: controller.reorder,
                    proxyDecorator: (child, index, animation) => Material(
                      type: MaterialType.transparency,
                      child: _CardTile(card: view.order[index], mark: null, lifted: true),
                    ),
                    itemBuilder: (context, i) => ReorderableDelayedDragStartListener(
                      key: ValueKey(view.order[i].id),
                      index: i,
                      enabled: !view.busy,
                      child: _CardTile(
                        card: view.order[i],
                        mark: view.markAt(i),
                        handle: ReorderableDragStartListener(
                          index: i,
                          enabled: !view.busy,
                          child: const Padding(
                            padding: EdgeInsets.all(8),
                            child: Icon(Icons.drag_indicator, color: Color(0xFFA0A8BC)),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: LU.accentStrong,
                minimumSize: const Size.fromHeight(56),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
              ),
              onPressed: view.busy ? null : controller.submit,
              child: view.busy
                  ? const SizedBox.square(
                      dimension: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : const Text('Kontrol et'),
            ),
          ),
        ],
      ),
    );
  }
}

/// Vertical value axis: the lower label on top, the higher one at the bottom.
class _Axis extends StatelessWidget {
  const _Axis({required this.lower, required this.higher});

  final String lower;
  final String higher;

  @override
  Widget build(BuildContext context) {
    const style = TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: LU.muted, letterSpacing: 0.4);
    return Semantics(
      label: 'Üstte $lower, altta $higher',
      excludeSemantics: true,
      child: SizedBox(
        width: 18,
        child: Column(
          children: [
            RotatedBox(quarterTurns: 3, child: Text(lower, style: style)),
            const SizedBox(height: 6),
            Expanded(
              child: Container(
                width: 4,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(2),
                  gradient: const LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [Color(0xFF7FB2FF), LU.primary, LU.accent],
                  ),
                ),
              ),
            ),
            const SizedBox(height: 6),
            RotatedBox(quarterTurns: 3, child: Text(higher, style: style)),
          ],
        ),
      ),
    );
  }
}

/// One card while ordering. [mark] is the last attempt's mark while the card is still where it was submitted.
class _CardTile extends StatelessWidget {
  const _CardTile({required this.card, required this.mark, this.handle, this.lifted = false});

  final GameCard card;
  final String? mark;
  final Widget? handle;

  /// Being dragged: primary color, shadow, nudged right.
  final bool lifted;

  @override
  Widget build(BuildContext context) {
    final fg = lifted ? Colors.white : LU.ink;
    final sub = [if (card.subtitle.isNotEmpty) card.subtitle, if (card.type.isNotEmpty) card.type].join(' · ');
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Transform.translate(
        offset: Offset(lifted ? 8 : 0, 0),
        child: Container(
          height: 64,
          padding: EdgeInsets.only(left: 16, right: handle == null ? 16 : 4),
          decoration: BoxDecoration(
            color: lifted ? LU.primary : LU.surface,
            borderRadius: BorderRadius.circular(18),
            boxShadow: lifted ? LU.liftShadow : LU.shadow,
          ),
          child: Row(
            children: [
              if (card.emoji.isNotEmpty) ...[
                Text(card.emoji, style: const TextStyle(fontSize: 22)),
                const SizedBox(width: 12),
              ],
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(card.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16, color: fg)),
                    if (sub.isNotEmpty)
                      Text(sub,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(fontSize: 12, color: lifted ? Colors.white70 : LU.muted)),
                  ],
                ),
              ),
              if (mark != null)
                Semantics(
                  label: switch (mark) {
                    markRight => 'önceki deneme: doğru yer',
                    markNear => 'önceki deneme: bir yer kaymış',
                    _ => 'önceki deneme: uzak',
                  },
                  child: MarkSquare(mark: mark, size: 22),
                ),
              ?handle,
            ],
          ),
        ),
      ),
    );
  }
}

class _Result extends ConsumerWidget {
  const _Result({required this.view, required this.number});

  final DailyView view;
  final int? number;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final puzzle = view.puzzle;
    final a = puzzle.attribute;
    final solved = puzzle.status == 'won';
    final streak = number == null ? ref.watch(homeProvider).value?.daily?.streak ?? 0 : 0;
    final line = [
      if (solved) '${puzzle.solvedIn}. denemede' else 'Doğru sıra aşağıda',
      if (streak > 0) 'seri $streak gün',
    ].join(' · ');
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      children: [
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(color: LU.surface, borderRadius: BorderRadius.circular(24), boxShadow: LU.shadow),
          child: Column(
            children: [
              Text(solved ? 'Çözdün!' : 'Bu sefer olmadı', style: display(28)),
              const SizedBox(height: 6),
              Text(line, style: const TextStyle(fontSize: 14, color: LU.muted)),
              const SizedBox(height: 14),
              _AttemptGrid(puzzle: puzzle, size: 34),
              const SizedBox(height: 16),
              if (puzzle.share != null)
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: () => SharePlus.instance.share(ShareParams(text: puzzle.share!)),
                    icon: const Icon(Icons.share),
                    label: const Text('Sonucu paylaş'),
                  ),
                ),
              if (!puzzle.archived) ...[
                const SizedBox(height: 10),
                _NextPuzzle(puzzle: puzzle, onReady: () => ref.invalidate(dailyProvider(number))),
              ],
            ],
          ),
        ),
        const SizedBox(height: 20),
        Text('Doğru sıra · ${a.name}, üstte ${a.lowerLabel}',
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: LU.muted, letterSpacing: 0.4)),
        const SizedBox(height: 8),
        for (final card in puzzle.solution) _SolutionTile(card: card),
        const SizedBox(height: 8),
        const Text('Bir kartta hata varsa bayrağa dokun.',
            style: TextStyle(fontSize: 12, color: LU.muted), textAlign: TextAlign.center),
      ],
    );
  }
}

class _SolutionTile extends ConsumerWidget {
  const _SolutionTile({required this.card});

  final GameCard card;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Material(
        color: LU.surface,
        borderRadius: BorderRadius.circular(14),
        child: InkWell(
          borderRadius: BorderRadius.circular(14),
          onLongPress: () => showCardReportDialog(context, ref, card, screen: 'daily'),
          child: Padding(
            padding: const EdgeInsets.only(left: 14),
            child: Row(
              children: [
                ConstrainedBox(
                  constraints: const BoxConstraints(minWidth: 56),
                  child: Text(card.value ?? '', style: display(16, color: LU.primary)),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(card.title,
                          maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 15)),
                      if (card.subtitle.isNotEmpty)
                        Text(card.subtitle,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 12, color: LU.muted)),
                    ],
                  ),
                ),
                _ReportButton(card: card),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// "Hata bildir" for one card (shared support API, `lineup.card`).
class _ReportButton extends ConsumerWidget {
  const _ReportButton({required this.card});

  final GameCard card;

  @override
  Widget build(BuildContext context, WidgetRef ref) => IconButton(
        icon: const Icon(Icons.outlined_flag, color: LU.muted),
        tooltip: 'Hata bildir',
        onPressed: () => showCardReportDialog(context, ref, card, screen: 'daily'),
      );
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
  Widget build(BuildContext context) => Text('Yeni bulmaca ${formatWait(_left)} sonra',
      textAlign: TextAlign.center, style: const TextStyle(fontSize: 13, color: LU.muted));
}
