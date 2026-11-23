import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/game_ui.dart';
import '../../core/theme.dart';
import '../billing/continue_offer.dart';
import '../home/energy_widgets.dart';
import '../home/home_data.dart';
import '../social/challenge_buttons.dart';
import '../support/card_report_dialog.dart';
import '../timeline/timeline_models.dart';
import 'streak_controller.dart';
import 'streak_models.dart';

const _higher = 'higher';
const _lower = 'lower';

/// Minimum height of the open and the hidden card (a two-line title fits), so nothing jumps between cards.
const _cardHeight = 168.0;

/// First letter upper-case, Turkish aware ("ileri" -> "İleri").
String _cap(String s) {
  if (s.isEmpty) return s;
  final first = switch (s[0]) { 'i' => 'İ', 'ı' => 'I', final c => c.toUpperCase() };
  return first + s.substring(1);
}

/// Streak mode: the open card shows its value; swipe the next card up (higher) or down (lower), or use the buttons.
/// One mistake ends the run. The server judges every guess. Layout: Phase 8 "Gündüz".
class StreakScreen extends ConsumerWidget {
  const StreakScreen({super.key, this.runId, this.challengeCode});

  /// A challenge run (null = the normal run being played, or the intro).
  final String? runId;
  final String? challengeCode;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final provider = streakProvider(runId);
    ref.listen(provider, (previous, next) {
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
    });

    final async = ref.watch(provider);
    final view = async.value;
    final run = view?.run;
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            GameHeader(
              title: challengeCode == null ? 'Seri' : 'Meydan okuma',
              trailing: run == null ? null : _Counter(score: run.score, best: run.best),
            ),
            Expanded(
              child: switch (async) {
                AsyncValue(hasError: true) => GameMessage(
                    text: '${async.error}',
                    action: 'Tekrar dene',
                    onAction: () => ref.invalidate(provider),
                  ),
                _ when view == null => const Center(child: CircularProgressIndicator()),
                _ when run == null => _Intro(busy: view.busy),
                _ => _Board(view: view, run: run, provider: provider, challengeCode: challengeCode),
              },
            ),
          ],
        ),
      ),
    );
  }
}

/// "7" over "rekor 14".
class _Counter extends StatelessWidget {
  const _Counter({required this.score, required this.best});

  final int score;
  final int best;

  @override
  Widget build(BuildContext context) => Semantics(
        label: 'Seri $score, rekor $best',
        excludeSemantics: true,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text('$score', style: display(22, color: LU.accentText)),
            Text('rekor $best', style: const TextStyle(fontSize: 12, color: LU.muted)),
          ],
        ),
      );
}

class _Intro extends ConsumerWidget {
  const _Intro({required this.busy});

  final bool busy;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final best = ref.watch(homeProvider).value?.bestStreak ?? 0;
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      children: [
        Text('Daha büyük mü, daha küçük mü?', style: display(26)),
        const SizedBox(height: 8),
        const Text(
          'Açık kartın değerini görürsün. Sıradaki kartı yukarı (daha büyük) ya da aşağı (daha küçük) kaydır. '
          'Her doğru tahmin serini uzatır; ilk hatada tur biter.',
          style: TextStyle(fontSize: 15, color: LU.muted, height: 1.4),
        ),
        const SizedBox(height: 20),
        if (best > 0)
          Panel(
            child: Row(
              children: [
                const Expanded(child: Text('Rekorun', style: TextStyle(fontSize: 15, color: LU.muted))),
                Text('$best', style: display(32, color: LU.accentText)),
              ],
            ),
          ),
        const SizedBox(height: 20),
        if (busy)
          const Center(child: CircularProgressIndicator())
        else
          FilledButton.icon(
            onPressed: () => ref.read(streakProvider(null).notifier).start(),
            icon: const Icon(Icons.bolt),
            label: const Text('Başla · 1 enerji'),
          ),
      ],
    );
  }
}

class _Board extends ConsumerWidget {
  const _Board({required this.view, required this.run, required this.provider, required this.challengeCode});

  final StreakView view;
  final StreakRun run;
  final AsyncNotifierProvider<StreakController, StreakView> provider;
  final String? challengeCode;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.read(provider.notifier);
    final a = run.attribute;
    final canGuess = run.isPlaying && run.current != null && !view.busy;
    void report(GameCard card) => showCardReportDialog(context, ref, card, screen: 'streak');
    final last = view.last;

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 10),
          child: Text(
            run.current == null ? a.name : '${a.name}: sıradaki kart açık karttan…',
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 15, color: LU.muted),
          ),
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                SizedBox(
                  width: 104,
                  child: _ValueAxis(
                    open: run.open,
                    history: run.history,
                    higher: a.higherLabel,
                    lower: a.lowerLabel,
                    onReport: report,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  // Top-aligned with fixed-height cards: the open card never moves.
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.start,
                    children: [
                      _OpenCard(
                        card: run.open,
                        // The card just revealed: green when the guess was right, red when wrong.
                        tint: last == null || last.card.id != run.open.id
                            ? null
                            : last.correct
                                ? const Color(0xFFDDF5E6)
                                : const Color(0xFFFDE4E4),
                        onReport: () => report(run.open),
                      ),
                      if (run.isPlaying && run.current != null) ...[
                        const SizedBox(height: 10),
                        _GuessButton(
                          label: _cap(a.higherLabel),
                          icon: Icons.arrow_upward,
                          bg: LU.primarySoft,
                          fg: LU.onPrimarySoft,
                          onPressed: canGuess ? () => controller.guess(_higher) : null,
                        ),
                        _SwipeCard(
                          key: ValueKey(run.current!.id),
                          card: run.current!,
                          enabled: canGuess,
                          busy: view.busy,
                          onGuess: controller.guess,
                        ),
                        _GuessButton(
                          label: _cap(a.lowerLabel),
                          icon: Icons.arrow_downward,
                          bg: LU.accentSoft,
                          fg: LU.onAccentSoft,
                          onPressed: canGuess ? () => controller.guess(_lower) : null,
                        ),
                      ] else
                        _EndPanel(run: run, busy: view.busy, provider: provider, challengeCode: challengeCode),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// Every revealed card on a vertical value axis, spread evenly: highest value on top (by `sort`, display only).
/// The open card's dot is blue. The axis does not scroll or re-centre.
class _ValueAxis extends StatelessWidget {
  const _ValueAxis({
    required this.open,
    required this.history,
    required this.higher,
    required this.lower,
    required this.onReport,
  });

  final GameCard open;
  final List<GameCard> history;
  final String higher;
  final String lower;
  final void Function(GameCard card) onReport;

  @override
  Widget build(BuildContext context) {
    final cards = <String, GameCard>{for (final c in history) c.id: c, open.id: open}.values.toList();
    final ordered = [...cards]..sort((a, b) => (a.sort ?? 0).compareTo(b.sort ?? 0));
    final highestFirst = ordered.reversed.toList();
    const labelStyle = TextStyle(fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.3);
    return Semantics(
      label: 'Değer ekseni: ${[for (final c in ordered.reversed) '${c.title} ${c.value ?? ''}'].join(', ')}',
      excludeSemantics: true,
      child: LayoutBuilder(
        builder: (context, box) {
          // Every card gets an equal share between the zone labels; nothing moves except new cards slotting in.
          const top = 40.0;
          final slot = (box.maxHeight - 2 * top) / highestFirst.length;
          final itemHeight = slot < 40 ? slot : 40.0;
          final compact = slot < 34; // value only when crowded
          return Stack(
            clipBehavior: Clip.hardEdge,
            children: [
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(18),
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        LU.primary.withValues(alpha: 0.10),
                        LU.primary.withValues(alpha: 0.02),
                        LU.accent.withValues(alpha: 0.03),
                        LU.accent.withValues(alpha: 0.12),
                      ],
                      stops: const [0, 0.5, 0.5, 1],
                    ),
                  ),
                ),
              ),
              Positioned(
                left: 8,
                right: 6,
                top: 8,
                child: Text('↑ $higher',
                    maxLines: 2, overflow: TextOverflow.ellipsis, style: labelStyle.copyWith(color: LU.onPrimarySoft)),
              ),
              Positioned(
                left: 8,
                right: 6,
                bottom: 8,
                child: Text('↓ $lower',
                    maxLines: 2, overflow: TextOverflow.ellipsis, style: labelStyle.copyWith(color: LU.onAccentSoft)),
              ),
              const Positioned(
                left: 15,
                top: 40,
                bottom: 40,
                child: SizedBox(width: 2, child: ColoredBox(color: Color(0xFFC3C9D6))),
              ),
              for (final (i, card) in highestFirst.indexed)
                _axisItem(card, top + slot * (i + 0.5), itemHeight, compact, card.id == open.id),
            ],
          );
        },
      ),
    );
  }

  Widget _axisItem(GameCard card, double y, double height, bool compact, bool isOpen) {
    final value = FittedBox(
      fit: BoxFit.scaleDown,
      alignment: Alignment.centerLeft,
      child: Text(card.value ?? '', style: display(14, color: isOpen ? LU.primary : LU.ink)),
    );
    return Positioned(
      key: ValueKey(card.id),
      left: 8,
      right: 4,
      top: y - height / 2,
      height: height,
      child: GestureDetector(
        onLongPress: () => onReport(card),
        child: Row(
          children: [
            SizedBox(
              width: 16,
              child: Center(
                child: Container(
                  width: isOpen ? 14 : 10,
                  height: isOpen ? 14 : 10,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: isOpen ? LU.primary : const Color(0xFF8E97AE),
                    boxShadow: isOpen ? [BoxShadow(color: LU.primary.withValues(alpha: 0.25), spreadRadius: 4)] : null,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 6),
            Expanded(
              // Crowded axis: the value alone, scaled into the row height.
              child: compact
                  ? value
                  : Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        value,
                        Text(card.title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                                fontSize: 11, color: LU.muted, fontWeight: isOpen ? FontWeight.w600 : FontWeight.w400)),
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _GuessButton extends StatelessWidget {
  const _GuessButton({required this.label, required this.icon, required this.bg, required this.fg, this.onPressed});

  final String label;
  final IconData icon;
  final Color bg;
  final Color fg;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) => SizedBox(
        width: double.infinity,
        child: FilledButton.icon(
          style: FilledButton.styleFrom(
            backgroundColor: bg,
            foregroundColor: fg,
            minimumSize: const Size.fromHeight(52),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
          ),
          onPressed: onPressed,
          icon: Icon(icon),
          label: Text(label, maxLines: 1, overflow: TextOverflow.ellipsis),
        ),
      );
}

/// The reference card: its value is shown big.
class _OpenCard extends StatelessWidget {
  const _OpenCard({required this.card, required this.onReport, this.tint});

  final GameCard card;
  final Color? tint;
  final VoidCallback onReport;

  @override
  Widget build(BuildContext context) {
    final sub = [if (card.subtitle.isNotEmpty) card.subtitle, if (card.type.isNotEmpty) card.type].join(' · ');
    return Container(
      width: double.infinity,
      // Room for a two-line title: the card keeps its size from card to card.
      constraints: const BoxConstraints(minHeight: _cardHeight),
      decoration: BoxDecoration(color: tint ?? LU.surface, borderRadius: BorderRadius.circular(22), boxShadow: LU.shadow),
      child: Material(
        type: MaterialType.transparency,
        child: InkWell(
          borderRadius: BorderRadius.circular(22),
          onLongPress: onReport,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Text('Açık kart',
                    style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: LU.muted, letterSpacing: 0.5)),
                const SizedBox(height: 2),
                Text('${card.emoji.isEmpty ? '' : '${card.emoji} '}${card.title}',
                    textAlign: TextAlign.center,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 19)),
                FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(card.value ?? '', textAlign: TextAlign.center, style: display(40, color: LU.primary)),
                ),
                if (sub.isNotEmpty)
                  Text(sub,
                      textAlign: TextAlign.center,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 13, color: LU.muted)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The hidden card: drag it up (higher) or down (lower) past a threshold, or flick it.
class _SwipeCard extends StatefulWidget {
  const _SwipeCard({super.key, required this.card, required this.enabled, required this.busy, required this.onGuess});

  final GameCard card;
  final bool enabled;
  final bool busy;
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
    final card = widget.card;
    final sub = [if (card.subtitle.isNotEmpty) card.subtitle, if (card.type.isNotEmpty) card.type].join(' · ');
    // Past the threshold the border shows which answer a release gives.
    final border = _dy <= -_threshold
        ? LU.primary
        : _dy >= _threshold
            ? LU.accent
            : Colors.transparent;
    return GestureDetector(
      onVerticalDragUpdate: widget.enabled ? (d) => setState(() => _dy = (_dy + d.delta.dy).clamp(-90.0, 90.0)) : null,
      onVerticalDragEnd: widget.enabled ? _end : null,
      child: Transform.translate(
        offset: Offset(0, _dy),
        child: Container(
          width: double.infinity,
          constraints: const BoxConstraints(minHeight: _cardHeight),
          margin: const EdgeInsets.symmetric(vertical: 10),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
          decoration: BoxDecoration(
            color: LU.ink,
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: border, width: 3),
            boxShadow: LU.liftShadow,
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text('${card.emoji.isEmpty ? '' : '${card.emoji} '}${card.title}',
                  textAlign: TextAlign.center,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 21)),
              Text('????',
                  style: display(34, color: Colors.white.withValues(alpha: 0.85)).copyWith(letterSpacing: 6)),
              if (sub.isNotEmpty)
                Text(sub,
                    textAlign: TextAlign.center,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: Colors.white70, fontSize: 13)),
              const SizedBox(height: 4),
              Text(widget.busy ? 'Kontrol ediliyor...' : 'Yukarı ya da aşağı kaydır',
                  style: const TextStyle(color: Colors.white60, fontSize: 12)),
            ],
          ),
        ),
      ),
    );
  }
}

class _EndPanel extends ConsumerWidget {
  const _EndPanel({required this.run, required this.busy, required this.provider, required this.challengeCode});

  final StreakRun run;
  final bool busy;
  final AsyncNotifierProvider<StreakController, StreakView> provider;

  /// Set for a challenge run: no new run from here, the result goes back to the challenge.
  final String? challengeCode;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final record = run.score > 0 && run.score >= run.best;
    final title = switch (run.status) {
      'finished' => 'Bütün kartları bildin!',
      _ => 'Seri bitti',
    };
    return Panel(
      margin: const EdgeInsets.only(top: 12),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(title, style: display(22), textAlign: TextAlign.center),
          const SizedBox(height: 4),
          Text(record ? 'Seri ${run.score} · yeni rekor!' : 'Seri ${run.score} · rekor ${run.best}',
              style: TextStyle(color: record ? LU.accentText : LU.muted, fontWeight: FontWeight.w600)),
          if (run.canContinue) ...[
            const SizedBox(height: 12),
            ContinueOffer(runId: run.id, onResumed: ref.read(provider.notifier).reload),
          ],
          if (challengeCode == null && !run.isPlaying) ...[
            const SizedBox(height: 8),
            ChallengeFromRunButton(runId: run.id),
          ],
          const SizedBox(height: 12),
          // Stacked: the column next to the value axis is narrow.
          SizedBox(
            width: double.infinity,
            child: challengeCode != null
                ? FilledButton(
                    onPressed: () => context.go('/home/challenges/$challengeCode'),
                    child: const Text('Sonucu gör'),
                  )
                : FilledButton(
                    onPressed: busy ? null : () => ref.read(provider.notifier).start(),
                    child: const Text('Yeni tur · ⚡1'),
                  ),
          ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton(onPressed: () => context.go('/home'), child: const Text('Ana menü')),
          ),
        ],
      ),
    );
  }
}
