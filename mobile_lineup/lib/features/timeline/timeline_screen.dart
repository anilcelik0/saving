import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/game_ui.dart';
import '../../core/theme.dart';
import '../billing/continue_offer.dart';
import '../home/energy_widgets.dart';
import '../social/challenge_buttons.dart';
import '../support/card_report_dialog.dart';
import 'timeline_controller.dart';
import 'timeline_models.dart';

/// Timeline mode (Phase 8 design): the line fills the screen, highest value on top; the new card waits at the bottom
/// with "?" for its value. Drag it freely: over the line it snaps into the nearest gap (the cards part) and letting go
/// places it there; after every move the next card comes in at the bottom. The start card is dragged onto the empty
/// line first (display only: the server already put it there). A wrong card simply disappears and a life is lost.
/// Every rule is checked by the server; there is no move timer.
class TimelineScreen extends ConsumerStatefulWidget {
  const TimelineScreen({super.key, this.runId, this.challengeCode});

  /// A challenge run (null = the normal run being played, or the difficulty picker).
  final String? runId;
  final String? challengeCode;

  @override
  ConsumerState<TimelineScreen> createState() => _TimelineScreenState();
}

/// The card just placed (or the start card just thrown) turns green until the next move.
const _rightTint = Color(0xFFDDF5E6);

class _TimelineScreenState extends ConsumerState<TimelineScreen> {
  late final _provider = timelineProvider(widget.runId);
  final _fieldKey = GlobalKey();

  /// Run whose start card was already thrown onto the line in this screen.
  String? _introDone;

  // Drag state, in field coordinates. Gaps are counted on screen: 0 = above the top (highest) card.
  Offset? _pointer;
  Offset _grab = Offset.zero;
  int? _hover;

  /// Gap sent to the server; the card stays snapped there until the answer.
  int? _pending;

  // Geometry of the last build, used while dragging.
  double _snapBelow = 0;
  List<double> _cardCenters = const [];

  bool _introActive(TimelineView view, RunState run) =>
      run.isPlaying &&
      run.line.length == 1 &&
      run.score == 0 &&
      run.lives >= 3 &&
      view.last == null &&
      _introDone != run.id;

  Offset? _toField(Offset global) {
    final box = _fieldKey.currentContext?.findRenderObject() as RenderBox?;
    return box?.globalToLocal(global);
  }

  /// Over the line: the gap below every card whose centre is above the finger; null below the line.
  int? _gapAt(Offset p) => p.dy > _snapBelow ? null : _cardCenters.where((c) => c < p.dy).length;

  void _dragStart(DragStartDetails d) {
    setState(() {
      _grab = d.localPosition;
      _pointer = _toField(d.globalPosition);
    });
  }

  void _dragCancel() => setState(() {
        _pointer = null;
        _hover = null;
      });

  void _dragUpdate(DragUpdateDetails d) {
    if (_pointer == null) return; // no drag started (e.g. while a move is being checked)
    final p = _toField(d.globalPosition);
    if (p == null) return;
    final gap = _gapAt(p);
    if (gap != _hover && gap != null) HapticFeedback.selectionClick();
    setState(() {
      _pointer = p;
      _hover = gap;
    });
  }

  void _dragEnd(RunState run, bool intro) {
    if (_pointer == null) return;
    final gap = _hover;
    setState(() {
      _pointer = null;
      _hover = null;
    });
    if (gap == null) return; // let go below the line: the card goes back
    if (intro) {
      HapticFeedback.lightImpact();
      setState(() => _introDone = run.id);
      return;
    }
    setState(() => _pending = gap);
    // The screen shows the highest value first; the server counts slots from the lowest.
    ref.read(_provider.notifier).place(run.line.length - gap);
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(_provider, (previous, next) {
      final view = next.value;
      if (view == null) return;
      if (view.error != null) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(view.error!)));
      }
      if (view.noEnergy) showNoEnergyDialog(context, ref);
      final last = view.last;
      if (last != null && !identical(last, previous?.value?.last)) {
        last.correct ? HapticFeedback.lightImpact() : HapticFeedback.heavyImpact();
      }
      if (!view.busy && _pending != null) setState(() => _pending = null);
    });

    final async = ref.watch(_provider);
    final view = async.value;
    final run = view?.run;
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            GameHeader(
              title: widget.challengeCode == null ? 'Zaman Çizgisi' : 'Meydan okuma',
              trailing: run == null ? null : Hearts(lives: run.lives),
            ),
            Expanded(
              child: switch (async) {
                AsyncValue(hasError: true) => GameMessage(
                    text: '${async.error}',
                    action: 'Tekrar dene',
                    onAction: () => ref.invalidate(_provider),
                  ),
                _ when view == null => const Center(child: CircularProgressIndicator()),
                _ when run == null => _DifficultyPicker(busy: view.busy),
                _ => _board(context, view, run),
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _board(BuildContext context, TimelineView view, RunState run) {
    final playing = run.isPlaying && run.current != null;
    final intro = _introActive(view, run);
    final a = run.attribute;
    final progress = run.goal == 0 ? 0.0 : math.min(1.0, run.score / run.goal);
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 0),
          child: Row(
            children: [
              Flexible(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(color: LU.primarySoft, borderRadius: BorderRadius.circular(14)),
                  child: Text('${a.name} · üstte ${a.higherLabel}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: LU.onPrimarySoft, fontSize: 13, fontWeight: FontWeight.w600)),
                ),
              ),
              const SizedBox(width: 12),
              Text.rich(
                TextSpan(children: [
                  TextSpan(text: '${run.score}', style: display(18)),
                  TextSpan(text: ' / ${run.goal} kart'),
                ]),
                style: const TextStyle(fontSize: 14, color: LU.muted),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 10, 20, 6),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(3),
            child: LinearProgressIndicator(value: progress, minHeight: 6, color: LU.primary, backgroundColor: LU.line),
          ),
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: LayoutBuilder(builder: (context, box) => _field(context, view, run, box.biggest, playing, intro)),
          ),
        ),
        if (playing)
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
            child: Text(
              intro
                  ? 'İlk kartı yukarı, çizgiye sürükle'
                  : view.busy
                      ? 'Kontrol ediliyor...'
                      : 'Kartı yukarı sürükle; boşluğa gelince oturur, bırakınca yerleşir',
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 13, color: LU.muted),
            ),
          )
        else
          _EndPanel(run: run, provider: _provider, challengeCode: widget.challengeCode),
      ],
    );
  }

  Widget _field(BuildContext context, TimelineView view, RunState run, Size size, bool playing, bool intro) {
    final last = view.last;
    // Highest value on top (the server's line is lowest first).
    final line = intro ? const <GameCard>[] : run.line.reversed.toList();
    final hand = intro ? run.line.first : run.current;
    final freshId = last != null
        ? (last.correct ? last.card.id : null)
        : (_introDone == run.id && run.line.length == 1 ? run.line.first.id : null);
    final handGap = _hover ?? (view.busy ? _pending : null);
    void report(GameCard card) => showCardReportDialog(context, ref, card, screen: 'timeline');

    const labelHeight = 20.0;
    const handHeight = 64.0;
    final handTop = size.height - handHeight;
    const lineTop = labelHeight + 6;
    final lineBottom = (playing ? handTop - 14 : size.height) - labelHeight - 6;

    // Top -> bottom: (card, isHand). The hand shows in the line while it is snapped into a gap.
    final entries = <(GameCard, bool)>[];
    for (var i = 0; i <= line.length; i++) {
      if (handGap == i && hand != null) entries.add((hand, true));
      if (i < line.length) entries.add((line[i], false));
    }
    // The whole line fits without scrolling: rows (then the spacing) shrink as it grows.
    final area = lineBottom - lineTop;
    final m = entries.length;
    var spacing = 8.0;
    var rowHeight = 56.0;
    if (m > 0) {
      rowHeight = (area - (m - 1) * spacing) / m;
      if (rowHeight < 30) {
        rowHeight = 30;
        if (m > 1) spacing = math.max(2.0, (area - m * rowHeight) / (m - 1));
      }
      rowHeight = math.min(rowHeight, 56.0);
    }
    final total = m * rowHeight + math.max(0, m - 1) * spacing;
    final startY = lineTop + math.max(0.0, (area - total) / 2);

    const labelStyle = TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: LU.muted);
    final children = <Widget>[
      Positioned(
        left: 0,
        right: 0,
        top: 0,
        child: Text('↑ ${run.attribute.higherLabel}', maxLines: 1, overflow: TextOverflow.ellipsis, style: labelStyle),
      ),
      Positioned(
        left: 0,
        right: 0,
        top: lineBottom + 6,
        child: Text('↓ ${run.attribute.lowerLabel}', maxLines: 1, overflow: TextOverflow.ellipsis, style: labelStyle),
      ),
    ];
    if (m == 0) {
      // Empty line: the start card has not been thrown yet.
      children.add(Positioned(
        left: 0,
        right: 0,
        top: lineTop,
        height: area,
        child: Container(
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: LU.primarySoft.withValues(alpha: 0.6),
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: LU.primary.withValues(alpha: 0.35), width: 1.5),
          ),
          child: const Text('Kartı buraya sürükle',
              style: TextStyle(color: LU.onPrimarySoft, fontWeight: FontWeight.w600)),
        ),
      ));
    }

    final centers = <double>[];
    for (final (k, (card, isHand)) in entries.indexed) {
      final top = startY + k * (rowHeight + spacing);
      if (!isHand) centers.add(top + rowHeight / 2);
      children.add(AnimatedPositioned(
        key: ValueKey(isHand ? 'slot' : card.id),
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOutCubic,
        left: 0,
        right: 0,
        top: top,
        height: rowHeight,
        child: isHand
            ? _LineCard(card: card, height: rowHeight, dark: true, hidden: true)
            : _LineCard(
                card: card,
                height: rowHeight,
                tint: card.id == freshId ? _rightTint : null,
                onReport: () => report(card),
              ),
      ));
    }
    _snapBelow = lineBottom + labelHeight;
    _cardCenters = centers;

    if (playing && hand != null) {
      final dragging = _pointer != null;
      final canDrag = !view.busy && _pending == null;
      // One keyed detector for the whole gesture (rebuilding it mid-drag would cancel the drag): the card at the
      // bottom turns invisible while a copy follows the finger or while it sits snapped in a gap.
      children.add(Positioned(
        key: const ValueKey('home'),
        left: 0,
        right: 0,
        top: handTop,
        height: handHeight,
        child: GestureDetector(
          onPanStart: canDrag ? _dragStart : null,
          onPanUpdate: _dragUpdate,
          onPanEnd: (_) => _dragEnd(run, intro),
          onPanCancel: _dragCancel,
          child: Opacity(
            opacity: dragging || handGap != null ? 0 : 1,
            child: _LineCard(card: hand, height: handHeight, dark: true, hidden: true, grip: true),
          ),
        ),
      ));
      if (dragging && _hover == null) {
        children.add(Positioned(
          key: const ValueKey('floating'),
          left: _pointer!.dx - _grab.dx,
          top: _pointer!.dy - _grab.dy,
          width: size.width,
          height: handHeight,
          child: IgnorePointer(
            child: Transform.rotate(
              angle: -0.03,
              child: _LineCard(card: hand, height: handHeight, dark: true, hidden: true, grip: true),
            ),
          ),
        ));
      }
    }
    return Stack(key: _fieldKey, clipBehavior: Clip.none, children: children);
  }
}

// ------------------------------------------------------------------ pieces

/// One row: value (Space Grotesk) and title. [dark] + [hidden] = the new card ("?"), at the bottom or snapped in a gap.
class _LineCard extends StatelessWidget {
  const _LineCard({
    required this.card,
    required this.height,
    this.onReport,
    this.tint,
    this.dark = false,
    this.hidden = false,
    this.grip = false,
  });

  final GameCard card;
  final double height;
  final VoidCallback? onReport;

  /// Last move feedback ([_rightTint]).
  final Color? tint;
  final bool dark;

  /// Value not known yet ("?").
  final bool hidden;

  /// The waiting card: an "up" hint on the right.
  final bool grip;

  @override
  Widget build(BuildContext context) {
    final fg = dark ? Colors.white : LU.ink;
    final sub = [if (card.subtitle.isNotEmpty) card.subtitle, if (card.type.isNotEmpty) card.type].join(' · ');
    return Container(
      height: height,
      decoration: BoxDecoration(
        color: dark ? LU.ink : (tint ?? LU.surface),
        borderRadius: BorderRadius.circular(14),
        boxShadow: dark ? LU.liftShadow : LU.shadow,
      ),
      child: Material(
        type: MaterialType.transparency,
        child: InkWell(
          onLongPress: onReport,
          borderRadius: BorderRadius.circular(14),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Row(
              children: [
                SizedBox(
                  width: 64,
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    alignment: Alignment.centerLeft,
                    child: Text(hidden ? '?' : (card.value ?? ''),
                        style: display(17, color: dark ? Colors.white : LU.primary)),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${card.emoji.isEmpty ? '' : '${card.emoji} '}${card.title}',
                          maxLines: height >= 48 ? 2 : 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14, color: fg, height: 1.2)),
                      if (height >= 60 && sub.isNotEmpty)
                        Text(sub,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(fontSize: 11, color: dark ? Colors.white70 : LU.muted)),
                    ],
                  ),
                ),
                if (grip) const Icon(Icons.north, color: Colors.white54, size: 20),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _DifficultyPicker extends ConsumerWidget {
  const _DifficultyPicker({required this.busy});

  final bool busy;

  static const _levels = [
    ('easy', 'Kolay', 'Tanınmış kartlar, değerler birbirinden uzak'),
    ('normal', 'Normal', 'Daha geniş kart havuzu, daha yakın değerler'),
    ('hard', 'Zor', 'Bütün kartlar, değerler çok yakın olabilir'),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.read(timelineProvider(null).notifier);
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      children: [
        Text('Kartları doğru sıraya diz', style: display(26)),
        const SizedBox(height: 8),
        const Text(
          'Her yeni kartı çizgide doğru yere koy. 10 kartlık çizgiyi tamamla; 3 hata hakkın var.',
          style: TextStyle(fontSize: 15, color: LU.muted, height: 1.4),
        ),
        const SizedBox(height: 24),
        if (busy)
          const Center(child: CircularProgressIndicator())
        else
          for (final (key, label, info) in _levels)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Material(
                color: LU.surface,
                borderRadius: BorderRadius.circular(20),
                child: InkWell(
                  borderRadius: BorderRadius.circular(20),
                  onTap: () => controller.start(key),
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(label, style: display(20)),
                              const SizedBox(height: 2),
                              Text(info, style: const TextStyle(fontSize: 13, color: LU.muted)),
                            ],
                          ),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                          decoration: BoxDecoration(color: LU.accentSoft, borderRadius: BorderRadius.circular(12)),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.bolt, size: 16, color: LU.onAccentSoft),
                              Text('1', style: TextStyle(color: LU.onAccentSoft, fontWeight: FontWeight.w700)),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
      ],
    );
  }
}

class _EndPanel extends ConsumerWidget {
  const _EndPanel({required this.run, required this.provider, required this.challengeCode});

  final RunState run;
  final AsyncNotifierProvider<TimelineController, TimelineView> provider;

  /// Set for a challenge run: no new run from here, the result goes back to the challenge.
  final String? challengeCode;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final title = switch (run.status) {
      'won' => 'Çizgiyi tamamladın!',
      'lost' => 'Hata hakkın bitti',
      _ => 'Kartlar bitti',
    };
    return Panel(
      margin: const EdgeInsets.fromLTRB(20, 8, 20, 16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(title, style: display(22), textAlign: TextAlign.center),
          const SizedBox(height: 4),
          Text('Skor ${run.score} / ${run.goal}', style: const TextStyle(color: LU.muted)),
          if (run.canContinue) ...[
            const SizedBox(height: 12),
            ContinueOffer(runId: run.id, onResumed: ref.read(provider.notifier).reload),
          ],
          if (challengeCode == null && !run.isPlaying) ...[
            const SizedBox(height: 8),
            ChallengeFromRunButton(runId: run.id),
          ],
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: challengeCode != null
                    ? FilledButton(
                        onPressed: () => context.go('/home/challenges/$challengeCode'),
                        child: const Text('Sonucu gör'),
                      )
                    : FilledButton(
                        onPressed: () => ref.read(provider.notifier).newRun(),
                        child: const Text('Yeni tur'),
                      ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: OutlinedButton(onPressed: () => context.go('/home'), child: const Text('Ana menü')),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
