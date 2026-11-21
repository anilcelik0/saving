import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../support/card_report_dialog.dart';
import 'timeline_controller.dart';
import 'timeline_models.dart';

/// Timeline mode: a vertical line (lower values on top), the new card at the bottom. Drag the card onto a gap,
/// or tap a gap. Every rule is checked by the server; the countdown only mirrors the server's timer.
class TimelineScreen extends ConsumerStatefulWidget {
  const TimelineScreen({super.key});

  @override
  ConsumerState<TimelineScreen> createState() => _TimelineScreenState();
}

class _TimelineScreenState extends ConsumerState<TimelineScreen> {
  final _scroll = ScrollController();
  final _listKey = GlobalKey();
  Timer? _autoScroll;
  double _scrollSpeed = 0;
  bool _dragging = false;

  @override
  void dispose() {
    _stopAutoScroll();
    _scroll.dispose();
    super.dispose();
  }

  // ------------------------------------------------------------ drag auto-scroll
  void _startAutoScroll() {
    setState(() => _dragging = true);
    _autoScroll = Timer.periodic(const Duration(milliseconds: 16), (_) {
      if (_scrollSpeed == 0 || !_scroll.hasClients) return;
      final position = _scroll.position;
      _scroll.jumpTo((position.pixels + _scrollSpeed).clamp(position.minScrollExtent, position.maxScrollExtent));
    });
  }

  void _stopAutoScroll() {
    _autoScroll?.cancel();
    _autoScroll = null;
    _scrollSpeed = 0;
    if (mounted && _dragging) setState(() => _dragging = false);
  }

  /// Near the top or bottom edge of the list the line scrolls by itself (faster closer to the edge).
  void _onDragUpdate(DragUpdateDetails details) {
    final box = _listKey.currentContext?.findRenderObject() as RenderBox?;
    if (box == null) return;
    final y = box.globalToLocal(details.globalPosition).dy;
    const edge = 72.0;
    final height = box.size.height;
    if (y < 0 || y > height) {
      _scrollSpeed = 0; // finger outside the line (e.g. still in the card panel)
    } else if (y < edge) {
      _scrollSpeed = -(edge - y) / 4;
    } else if (y > height - edge) {
      _scrollSpeed = (y - (height - edge)) / 4;
    } else {
      _scrollSpeed = 0;
    }
  }

  void _place(int? slot) {
    _stopAutoScroll();
    ref.read(timelineProvider.notifier).place(slot);
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(timelineProvider, (previous, next) {
      final view = next.value;
      if (view == null) return;
      if (view.error != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(view.error!), behavior: SnackBarBehavior.floating),
        );
      }
      final last = view.last;
      if (last != null && !identical(last, previous?.value?.last)) {
        last.correct ? HapticFeedback.lightImpact() : HapticFeedback.heavyImpact();
      }
    });

    final async = ref.watch(timelineProvider);
    final view = async.value;
    final run = view?.run;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Zaman Çizgisi'),
        actions: [
          if (run != null) ...[
            for (var i = 0; i < 3; i++)
              Icon(i < run.lives ? Icons.favorite : Icons.favorite_border, color: Colors.red, size: 20),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Center(child: Text('${run.score}/${run.goal}', style: Theme.of(context).textTheme.titleMedium)),
            ),
          ],
        ],
      ),
      body: SafeArea(
        child: switch (async) {
          AsyncValue(hasError: true) => _Message(
              text: '${async.error}',
              action: 'Tekrar dene',
              onAction: () => ref.invalidate(timelineProvider),
            ),
          _ when view == null => const Center(child: CircularProgressIndicator()),
          _ when run == null => _DifficultyPicker(busy: view.busy),
          _ => _board(context, view, run),
        },
      ),
    );
  }

  Widget _board(BuildContext context, TimelineView view, RunState run) {
    final theme = Theme.of(context);
    final last = view.last;
    final canPlace = run.isPlaying && run.current != null && !view.busy;
    final children = <Widget>[];
    for (var i = 0; i <= run.line.length; i++) {
      children.add(_Gap(index: i, enabled: canPlace, dragging: _dragging, onPlace: _place));
      if (i < run.line.length) {
        final card = run.line[i];
        children.add(_LineStrip(
          card: card,
          fresh: last != null && last.correct && last.card.id == card.id,
          onReport: () => showCardReportDialog(context, ref, card, screen: 'timeline'),
        ));
      }
    }
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: Text('${run.attribute.name}:  ↑ ${run.attribute.lowerLabel}  ·  ${run.attribute.higherLabel} ↓',
              style: theme.textTheme.labelLarge),
        ),
        if (last != null)
          _ResultBanner(
            result: last,
            onReport: () => showCardReportDialog(context, ref, last.card, screen: 'timeline'),
          ),
        Expanded(
          child: ListView(
            key: _listKey,
            controller: _scroll,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            children: children,
          ),
        ),
        const Divider(height: 1),
        if (run.isPlaying && run.current != null)
          _CurrentCardPanel(
            run: run,
            busy: view.busy,
            onExpired: () => _place(null),
            onDragStarted: _startAutoScroll,
            onDragUpdate: _onDragUpdate,
            onDragFinished: _stopAutoScroll,
          )
        else
          _EndPanel(run: run),
      ],
    );
  }
}

// ------------------------------------------------------------------ pieces
class _DifficultyPicker extends ConsumerWidget {
  const _DifficultyPicker({required this.busy});

  final bool busy;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.read(timelineProvider.notifier);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Kartları doğru sıraya diz', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            const Text('Her yeni kartı çizgide doğru yere koy. 10 kartlık çizgiyi tamamla; 3 hata hakkın var, '
                'her kart için 10 saniyen var.', textAlign: TextAlign.center),
            const SizedBox(height: 24),
            if (busy)
              const CircularProgressIndicator()
            else
              for (final (key, label) in const [('easy', 'Kolay'), ('normal', 'Normal'), ('hard', 'Zor')])
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: SizedBox(
                    width: 220,
                    child: FilledButton.tonal(onPressed: () => controller.start(key), child: Text(label)),
                  ),
                ),
          ],
        ),
      ),
    );
  }
}

class _Gap extends StatelessWidget {
  const _Gap({required this.index, required this.enabled, required this.dragging, required this.onPlace});

  final int index;
  final bool enabled;
  final bool dragging;
  final void Function(int slot) onPlace;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return DragTarget<String>(
      onWillAcceptWithDetails: (_) => enabled,
      onAcceptWithDetails: (_) => onPlace(index),
      builder: (context, candidates, rejected) {
        final hovering = candidates.isNotEmpty;
        return InkWell(
          borderRadius: BorderRadius.circular(8),
          onTap: enabled ? () => onPlace(index) : null,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 120),
            height: hovering ? 56 : (dragging ? 36 : 26),
            margin: const EdgeInsets.symmetric(vertical: 2),
            decoration: BoxDecoration(
              color: hovering ? scheme.primaryContainer : null,
              border: Border.all(color: hovering ? scheme.primary : scheme.outlineVariant),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Center(
              child: Icon(Icons.add, size: 16, color: enabled ? scheme.primary : scheme.outlineVariant),
            ),
          ),
        );
      },
    );
  }
}

class _LineStrip extends StatelessWidget {
  const _LineStrip({required this.card, required this.fresh, required this.onReport});

  final GameCard card;
  final bool fresh;
  final VoidCallback onReport;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: EdgeInsets.zero,
      color: fresh ? Colors.green.shade50 : null,
      child: InkWell(
        onLongPress: onReport,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Row(
            children: [
              SizedBox(
                width: 120,
                child: Text(card.value ?? '', style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.bold)),
              ),
              Expanded(
                child: Text(
                  card.subtitle.isEmpty ? card.title : '${card.title} (${card.subtitle})',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (card.emoji.isNotEmpty) Text(card.emoji),
            ],
          ),
        ),
      ),
    );
  }
}

class _BigCard extends StatelessWidget {
  const _BigCard({required this.card});

  final GameCard card;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      elevation: 3,
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
          ],
        ),
      ),
    );
  }
}

class _CurrentCardPanel extends StatelessWidget {
  const _CurrentCardPanel({
    required this.run,
    required this.busy,
    required this.onExpired,
    required this.onDragStarted,
    required this.onDragUpdate,
    required this.onDragFinished,
  });

  final RunState run;
  final bool busy;
  final VoidCallback onExpired;
  final VoidCallback onDragStarted;
  final void Function(DragUpdateDetails) onDragUpdate;
  final VoidCallback onDragFinished;

  @override
  Widget build(BuildContext context) {
    final card = run.current!;
    final width = MediaQuery.sizeOf(context).width - 32;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _Countdown(
            key: ValueKey(card.id),
            totalMs: run.moveSeconds * 1000,
            remainingMs: run.remainingMs ?? run.moveSeconds * 1000,
            onExpired: onExpired,
          ),
          const SizedBox(height: 8),
          Draggable<String>(
            data: card.id,
            maxSimultaneousDrags: busy ? 0 : 1,
            onDragStarted: onDragStarted,
            onDragUpdate: onDragUpdate,
            onDragEnd: (_) => onDragFinished(),
            feedback: Material(
              color: Colors.transparent,
              child: SizedBox(width: width * 0.85, child: Opacity(opacity: 0.9, child: _BigCard(card: card))),
            ),
            childWhenDragging: Opacity(opacity: 0.3, child: _BigCard(card: card)),
            child: _BigCard(card: card),
          ),
          Text(busy ? 'Kontrol ediliyor...' : 'Kartı çizgide doğru yere sürükle ya da bir boşluğa dokun',
              style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }
}

/// Mirrors the server's move timer; when it runs out the client reports a timeout (the server checks it anyway).
class _Countdown extends StatefulWidget {
  const _Countdown({super.key, required this.totalMs, required this.remainingMs, required this.onExpired});

  final int totalMs;
  final int remainingMs;
  final VoidCallback onExpired;

  @override
  State<_Countdown> createState() => _CountdownState();
}

class _CountdownState extends State<_Countdown> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: Duration(milliseconds: widget.totalMs))
      ..addStatusListener((status) {
        if (status == AnimationStatus.dismissed) widget.onExpired();
      })
      ..reverse(from: (widget.remainingMs / widget.totalMs).clamp(0.0, 1.0));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final seconds = (_controller.value * widget.totalMs / 1000).ceil();
        final low = _controller.value < 0.3;
        return Row(
          children: [
            Expanded(
              child: LinearProgressIndicator(
                value: _controller.value,
                minHeight: 6,
                color: low ? Colors.red : null,
                borderRadius: BorderRadius.circular(3),
              ),
            ),
            const SizedBox(width: 8),
            SizedBox(width: 28, child: Text('$seconds sn', textAlign: TextAlign.end)),
          ],
        );
      },
    );
  }
}

class _ResultBanner extends StatelessWidget {
  const _ResultBanner({required this.result, required this.onReport});

  final MoveResult result;
  final VoidCallback onReport;

  @override
  Widget build(BuildContext context) {
    final ok = result.correct;
    final label = ok ? 'Doğru!' : (result.timedOut ? 'Süre doldu' : 'Yanlış yer');
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
  const _EndPanel({required this.run});

  final RunState run;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final title = switch (run.status) {
      'won' => 'Tebrikler, çizgiyi tamamladın!',
      'lost' => 'Hata hakkın bitti',
      _ => 'Kartlar bitti',
    };
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleLarge),
          Text('Skor: ${run.score}/${run.goal}'),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              FilledButton(onPressed: () => ref.read(timelineProvider.notifier).newRun(), child: const Text('Yeni tur')),
              const SizedBox(width: 12),
              OutlinedButton(onPressed: () => context.go('/home'), child: const Text('Ana menü')),
            ],
          ),
        ],
      ),
    );
  }
}

class _Message extends StatelessWidget {
  const _Message({required this.text, required this.action, required this.onAction});

  final String text;
  final String action;
  final VoidCallback onAction;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(padding: const EdgeInsets.all(24), child: Text(text, textAlign: TextAlign.center)),
          FilledButton(onPressed: onAction, child: Text(action)),
        ],
      ),
    );
  }
}
