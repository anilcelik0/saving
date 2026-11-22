import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/api_client.dart';
import 'challenge_data.dart';

String outcomeText(String? outcome) => switch (outcome) {
      'win' => 'Kazandın',
      'lose' => 'Kaybettin',
      'tie' => 'Berabere',
      _ => 'Oynanıyor',
    };

/// Incoming, played and sent challenges + join by code.
class ChallengesScreen extends ConsumerStatefulWidget {
  const ChallengesScreen({super.key});

  @override
  ConsumerState<ChallengesScreen> createState() => _ChallengesScreenState();
}

class _ChallengesScreenState extends ConsumerState<ChallengesScreen> {
  final _code = TextEditingController();

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  void _join() {
    final code = _code.text.trim().toUpperCase();
    if (code.length < 4) return;
    context.push('/home/challenges/$code');
  }

  @override
  Widget build(BuildContext context) {
    final lists = ref.watch(challengeListsProvider);
    final theme = Theme.of(context);
    Widget section(String title, List<ChallengeRow> rows, Widget Function(ChallengeRow) tile, String empty) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 16),
            Text(title, style: theme.textTheme.titleMedium),
            if (rows.isEmpty) Padding(padding: const EdgeInsets.all(8), child: Text(empty, style: theme.textTheme.bodySmall)),
            for (final r in rows) tile(r),
          ],
        );
    ListTile row(ChallengeRow r, String subtitle) => ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text('${r.modeLabel} · ${r.attribute}'),
          subtitle: Text(subtitle),
          trailing: const Icon(Icons.chevron_right),
          onTap: () async {
            await context.push('/home/challenges/${r.code}');
            ref.invalidate(challengeListsProvider);
          },
        );
    return Scaffold(
      appBar: AppBar(title: const Text('Meydan okumalar')),
      body: RefreshIndicator(
        onRefresh: () => ref.refresh(challengeListsProvider.future),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _code,
                    textCapitalization: TextCapitalization.characters,
                    autocorrect: false,
                    onSubmitted: (_) => _join(),
                    decoration: const InputDecoration(labelText: 'Kodla katıl', border: OutlineInputBorder()),
                  ),
                ),
                const SizedBox(width: 8),
                FilledButton(onPressed: _join, child: const Text('Aç')),
              ],
            ),
            const SizedBox(height: 8),
            Text('Meydan okumak için bir Zaman Çizgisi ya da Seri turunu bitir, sonra "Arkadaşına meydan oku".',
                style: theme.textTheme.bodySmall),
            switch (lists) {
              AsyncValue(:final value?) => Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    section('Gelen', value.incoming,
                        (r) => row(r, '${r.creator} · hedef ${r.creatorScore}'), 'Sana gönderilen meydan okuma yok.'),
                    section('Oynadıklarım', value.played,
                        (r) => row(r, '${r.creator}: ${r.creatorScore} · sen: ${r.myEntry?.score ?? '-'} · '
                            '${outcomeText(r.myEntry?.outcome)}'),
                        'Henüz bir meydan okuma oynamadın.'),
                    section('Gönderdiklerim', value.sent,
                        (r) => row(r, 'skorun ${r.creatorScore} · ${r.entries ?? 0} kişi oynadı'
                            '${r.expired ? ' · süresi doldu' : ''}'),
                        'Henüz meydan okumadın.'),
                  ],
                ),
              AsyncValue(:final error?) => ListTile(
                  leading: const Icon(Icons.error_outline),
                  title: Text('$error'),
                  onTap: () => ref.invalidate(challengeListsProvider),
                ),
              _ => const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator())),
            },
          ],
        ),
      ),
    );
  }
}

/// One challenge: the creator shares / sends it and sees results; others accept (free) and compare.
class ChallengeScreen extends ConsumerStatefulWidget {
  const ChallengeScreen({super.key, required this.code});

  final String code;

  @override
  ConsumerState<ChallengeScreen> createState() => _ChallengeScreenState();
}

class _ChallengeScreenState extends ConsumerState<ChallengeScreen> {
  final _username = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _username.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _play(Challenge c) => _run(() async {
        final runId = await ref.read(socialApiProvider).accept(c.code);
        if (!mounted) return;
        await context.push(c.playRoute(runId));
        ref.invalidate(challengeProvider(widget.code));
      });

  Future<void> _send(Challenge c) => _run(() async {
        final name = _username.text.trim();
        if (name.isEmpty) return;
        await ref.read(socialApiProvider).send(c.code, name);
        _username.clear();
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$name kişisine gönderildi.')));
      });

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(challengeProvider(widget.code.toUpperCase()));
    return Scaffold(
      appBar: AppBar(title: Text('Meydan okuma ${widget.code.toUpperCase()}')),
      body: switch (async) {
        AsyncValue(:final value?) => RefreshIndicator(
            onRefresh: () => ref.refresh(challengeProvider(widget.code.toUpperCase()).future),
            child: _body(context, value),
          ),
        AsyncValue(:final error?) => Center(
            child: Padding(padding: const EdgeInsets.all(24), child: Text('$error', textAlign: TextAlign.center)),
          ),
        _ => const Center(child: CircularProgressIndicator()),
      },
    );
  }

  Widget _body(BuildContext context, Challenge c) {
    final theme = Theme.of(context);
    final mine = c.myEntry;
    final unit = c.mode == 'timeline' ? 'kart' : 'seri';
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(c.isCreator ? 'Senin meydan okuman' : '${c.creator} sana meydan okuyor',
            style: theme.textTheme.titleLarge),
        Text('${c.modeLabel} · ${c.attribute}'),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: const Icon(Icons.flag),
            title: Text('Hedef: ${c.creatorScore} $unit'),
            subtitle: Text(c.expired
                ? 'Süresi doldu'
                : 'Son gün: ${c.expiresAt.day}.${c.expiresAt.month}.${c.expiresAt.year} · aynı kartlar, aynı sıra'),
          ),
        ),
        if (c.isCreator) ...[
          const SizedBox(height: 8),
          FilledButton.icon(
            onPressed: c.expired ? null : () => SharePlus.instance.share(ShareParams(text: c.shareText)),
            icon: const Icon(Icons.share),
            label: const Text('Linki paylaş'),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _username,
                  autocorrect: false,
                  decoration: const InputDecoration(labelText: 'Kullanıcı adına gönder', border: OutlineInputBorder()),
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(onPressed: _busy || c.expired ? null : () => _send(c), child: const Text('Gönder')),
            ],
          ),
        ] else if (mine == null) ...[
          const SizedBox(height: 8),
          FilledButton.icon(
            onPressed: _busy || c.expired ? null : () => _play(c),
            icon: const Icon(Icons.play_arrow),
            label: const Text('Kabul et ve oyna (ücretsiz)'),
          ),
        ] else if (!mine.finished) ...[
          const SizedBox(height: 8),
          FilledButton.icon(
            onPressed: _busy ? null : () => _play(c),
            icon: const Icon(Icons.play_arrow),
            label: Text('Devam et · şu an ${mine.score}'),
          ),
        ] else
          Card(
            color: switch (mine.outcome) {
              'win' => Colors.green.shade100,
              'lose' => Colors.red.shade100,
              _ => null,
            },
            child: ListTile(
              leading: const Icon(Icons.emoji_events),
              title: Text('${outcomeText(mine.outcome)}!'),
              subtitle: Text('Sen ${mine.score} – ${c.creator} ${c.creatorScore}'),
            ),
          ),
        const SizedBox(height: 16),
        Text('Oynayanlar', style: theme.textTheme.titleMedium),
        if (c.entries.isEmpty)
          Padding(
            padding: const EdgeInsets.all(8),
            child: Text('Henüz kimse oynamadı.', style: theme.textTheme.bodySmall),
          ),
        for (final e in c.entries)
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: Icon(e.finished ? Icons.check_circle_outline : Icons.hourglass_empty),
            title: Text(e.username),
            subtitle: Text(e.finished
                ? '${e.score} $unit · ${switch (e.outcome) {
                    'win' => '${c.creator} kaybetti',
                    'lose' => '${c.creator} kazandı',
                    _ => 'berabere',
                  }}'
                : 'oynuyor'),
          ),
      ],
    );
  }
}
