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
/// with "?" for its value. Drag it up: it stays under the finger while the cards part smoothly where it would go
/// (no magnet); letting go glides it into that gap and places it, and the next card slides in at the bottom. The start
/// card is dragged onto the empty line first (display only: the server already put it there). A wrong card simply
/// disappears and a life is lost. Every rule is checked by the server; there is no move timer.
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
const _handHeight = 64.0;

/// Where things are in the play field. Highest value on top; gap 0 = above the top card.
class _Geometry {
  const _Geometry({
    required this.width,
    required this.startY,
    required this.row,
    required this.spacing,
    required this.lineBottom,
    required this.home,
    required this.count,
    required this.restOffset,
  });

  final double width;
  final double startY;
  final double row;
  final double spacing;

  /// Below this the card is back over its waiting place: no gap opens.
  final double lineBottom;

  /// The waiting card's place at the bottom.
  final Rect home;

  /// Cards on the line.
  final int count;

  /// 0.5 while playing: the line rests centred in room for one more row, so an open gap parts it symmetrically and
  /// a placed card ends up exactly where it was dropped.
  final double restOffset;

  double get pitch => row + spacing;

  /// Top of line card [k]; with [open] set, the cards part around that gap.
  double cardTop(int k, int? open) => startY + (open == null ? k + restOffset : (k < open ? k : k + 1)) * pitch;

  Rect slot(int gap) => Rect.fromLTWH(0, startY + gap * pitch, width, row);

  /// The gap under a card centred at [y], judged against the resting line so it never flickers while cards move.
  int? gapAt(double y) {
    if (y > lineBottom) return null;
    var gap = 0;
    for (var k = 0; k < count; k++) {
      if (cardTop(k, null) + row / 2 < y) gap++;
    }
    return gap;
  }
}

class _TimelineScreenState extends ConsumerState<TimelineScreen> with SingleTickerProviderStateMixin {
  late final _provider = timelineProvider(widget.runId);

  /// After letting go the card glides into its gap (or back to its waiting place).
  late final AnimationController _glide;

  /// Run whose start card was already thrown onto the line in this screen.
  String? _introDone;
  _Geometry? _geo;

  // Drag: the card's top-left in field coordinates and the gap it is over.
  Offset? _cardAt;
  int? _over;
  RunState? _dragRun;
  bool _dragIntro = false;

  // Glide after letting go.
  Rect? _glideFrom;
  Rect? _glideTo;
  int? _glideGap;

  /// Gap sent to the server; the card waits there until the answer.
  int? _pending;

  @override
  void initState() {
    super.initState();
    _glide = AnimationController(vsync: this, duration: const Duration(milliseconds: 240))
      ..addListener(() => setState(() {}))
      ..addStatusListener(_glided);
  }

  @override
  void dispose() {
    _glide.dispose();
    super.dispose();
  }

  bool _introActive(TimelineView view, RunState run) =>
      run.isPlaying &&
      run.line.length == 1 &&
      run.score == 0 &&
      run.lives >= 3 &&
      view.last == null &&
      _introDone != run.id;

  void _dragStart(RunState run, bool intro) {
    final geo = _geo;
    if (geo == null || _glide.isAnimating) return;
    setState(() {
      _cardAt = geo.home.topLeft;
      _dragRun = run;
      _dragIntro = intro;
    });
  }

  void _dragUpdate(DragUpdateDetails d) {
    final geo = _geo;
    final at = _cardAt;
    if (geo == null || at == null) return; // no drag started (e.g. while a move is being checked)
    final next = at + d.delta;
    final gap = geo.gapAt(next.dy + _handHeight / 2);
    if (gap != _over && gap != null) HapticFeedback.selectionClick();
    setState(() {
      _cardAt = next;
      _over = gap;
    });
  }

  void _dragEnd() {
    final geo = _geo;
    final at = _cardAt;
    if (geo == null || at == null) return;
    final gap = _over;
    setState(() {
      _glideFrom = at & geo.home.size;
      _glideTo = gap == null ? geo.home : geo.slot(gap);
      _glideGap = gap;
      _cardAt = null; // _over stays: the gap is kept open while the card glides into it
    });
    _glide.forward(from: 0);
  }

  void _glided(AnimationStatus status) {
    if (status != AnimationStatus.completed) return;
    final gap = _glideGap;
    final run = _dragRun;
    final intro = _dragIntro;
    setState(() {
      _glideFrom = null;
      _glideTo = null;
      _glideGap = null;
      _over = null;
      if (gap != null && run != null) {
        if (intro) {
          _introDone = run.id;
        } else {
          _pending = gap;
        }
      }
    });
    if (gap == null || run == null) return;
    if (intro) {
      HapticFeedback.lightImpact();
      return;
    }
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
                  : view.busy || _pending != null
                      ? 'Kontrol ediliyor...'
                      : 'Kartı yukarı sürükle, kartlar aralanınca bırak',
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
    void report(GameCard card) => showCardReportDialog(context, ref, card, screen: 'timeline');

    const labelHeight = 20.0;
    final home = Rect.fromLTWH(0, size.height - _handHeight, size.width, _handHeight);
    const lineTop = labelHeight + 6;
    final lineBottom = (playing ? home.top - 14 : size.height) - labelHeight - 6;
    final area = lineBottom - lineTop;
    // The whole line fits without scrolling: rows (then the spacing) shrink as it grows. While playing there is room
    // for one more row (the card being placed).
    final rows = line.length + (playing ? 1 : 0);
    var spacing = 8.0;
    var row = 56.0;
    if (rows > 0) {
      row = (area - (rows - 1) * spacing) / rows;
      if (row < 30) {
        row = 30;
        if (rows > 1) spacing = math.max(2.0, (area - rows * row) / (rows - 1));
      }
      row = math.min(row, 56.0);
    }
    final total = rows * row + math.max(0, rows - 1) * spacing;
    final geo = _Geometry(
      width: size.width,
      startY: lineTop + math.max(0.0, (area - total) / 2),
      row: row,
      spacing: spacing,
      lineBottom: lineBottom,
      home: home,
      count: line.length,
      restOffset: playing ? 0.5 : 0,
    );
    _geo = geo;
    final open = _over ?? _pending;

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
      if (intro)
        // Empty line: the start card has not been thrown yet.
        Positioned(
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
        ),
    ];

    for (final (k, card) in line.indexed) {
      children.add(AnimatedPositioned(
        key: ValueKey(card.id),
        duration: const Duration(milliseconds: 260),
        curve: Curves.easeOutCubic,
        left: 0,
        width: geo.width,
        top: geo.cardTop(k, open),
        height: row,
        child: _LineCard(
          card: card,
          height: row,
          tint: card.id == freshId ? _rightTint : null,
          onReport: () => report(card),
        ),
      ));
    }

    if (playing && hand != null) {
      // Waiting for the server: the card sits in its gap (same key as the card it becomes on the line, so a right
      // answer turns it over in place).
      if (_pending != null && _glideFrom == null) {
        final r = geo.slot(_pending!);
        children.add(AnimatedPositioned(
          key: ValueKey(hand.id),
          duration: const Duration(milliseconds: 260),
          curve: Curves.easeOutCubic,
          left: r.left,
          width: r.width,
          top: r.top,
          height: r.height,
          child: _LineCard(card: hand, height: r.height, dark: true, hidden: true),
        ));
      }

      final moving = _cardAt != null || _glideFrom != null;
      final canDrag = !view.busy && _pending == null && !_glide.isAnimating;
      // One keyed detector for the whole gesture (rebuilding it mid-drag would cancel the drag); the waiting card
      // hides while it is in the hand. The next card slides in from below.
      children.add(Positioned(
        key: const ValueKey('home'),
        left: home.left,
        width: home.width,
        top: home.top,
        height: home.height,
        child: GestureDetector(
          onPanStart: canDrag ? (_) => _dragStart(run, intro) : null,
          onPanUpdate: _dragUpdate,
          onPanEnd: (_) => _dragEnd(),
          onPanCancel: _dragEnd,
          child: Opacity(
            opacity: moving || _pending != null ? 0 : 1,
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 280),
              layoutBuilder: (current, previous) => current ?? const SizedBox.shrink(),
              transitionBuilder: (child, animation) => FadeTransition(
                opacity: animation,
                child: SlideTransition(
                  position: Tween(begin: const Offset(0, 0.6), end: Offset.zero)
                      .animate(CurvedAnimation(parent: animation, curve: Curves.easeOutCubic)),
                  child: child,
                ),
              ),
              child: _LineCard(
                key: ValueKey(hand.id),
                card: hand,
                height: _handHeight,
                dark: true,
                hidden: true,
                grip: true,
              ),
            ),
          ),
        ),
      ));

      // The card in the hand: under the finger, then gliding; drawn last so it stays on top.
      Rect? rect;
      var angle = 0.0;
      if (_cardAt != null) {
        rect = _cardAt! & home.size;
        angle = -0.025;
      } else if (_glideFrom != null && _glideTo != null) {
        final t = Curves.easeOutCubic.transform(_glide.value);
        rect = Rect.lerp(_glideFrom, _glideTo, t);
        angle = -0.025 * (1 - t);
      }
      if (rect != null) {
        children.add(AnimatedPositioned(
          key: ValueKey(hand.id),
          duration: Duration.zero,
          left: rect.left,
          width: rect.width,
          top: rect.top,
          height: rect.height,
          child: IgnorePointer(
            child: Transform.rotate(
              angle: angle,
              child: _LineCard(card: hand, height: rect.height, dark: true, hidden: true, grip: rect.height >= 60),
            ),
          ),
        ));
      }
    }
    return Stack(clipBehavior: Clip.none, children: children);
  }
}

// ------------------------------------------------------------------ pieces

/// One row: value (Space Grotesk) and title. [dark] + [hidden] = the new card ("?"), waiting, in the hand or in a gap.
class _LineCard extends StatelessWidget {
  const _LineCard({
    super.key,
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
    return AnimatedContainer(
      duration: const Duration(milliseconds: 260),
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
