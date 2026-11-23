import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../config.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../notifications/local_notices.dart';
import '../session/session_controller.dart';
import '../social/challenge_data.dart';
import 'energy_widgets.dart';
import 'home_data.dart';

/// Backend health (`/api/v1/health/`): a small footer line until release (deploy check, PROGRESS 9.0).
final _healthProvider = FutureProvider.autoDispose<String>((ref) async {
  final data = await ref.watch(apiClientProvider).get('health/', auth: false);
  return '${data['status']}';
});

/// Main menu (Phase 8 "Gündüz" design): energy, today's puzzle as the big card, the two modes side by side,
/// challenges and Pro. A run being played is resumed from its tile.
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider).value;
    if (session is! SessionReady) return const Scaffold();
    final user = session.user;
    final health = ref.watch(_healthProvider);
    ref.watch(dailyReminderProvider);
    ref.listen(homeProvider, (_, next) {
      final e = next.value?.energy;
      if (e != null) ref.read(localNoticesProvider).energyFullIn(e.unlimited ? null : e.fullInSeconds);
    });
    final home = ref.watch(homeProvider);
    final info = home.value;
    final timeline = info?.playing['timeline'];
    final streak = info?.playing['streak'];
    final energy = info?.energy;
    final cost = energy == null ? null : (energy.unlimited ? 'Sınırsız' : '${energy.cost} enerji');
    final incoming = ref.watch(challengeListsProvider).value?.incoming.length ?? 0;
    final timelineWins = info?.timelineWins ?? 0;
    final bestStreak = info?.bestStreak ?? 0;
    final pro = info?.pro.active ?? false;

    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () {
            ref.invalidate(challengeListsProvider);
            return ref.refresh(homeProvider.future);
          },
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text.rich(
                      const TextSpan(children: [
                        TextSpan(text: 'Line'),
                        TextSpan(text: 'Up', style: TextStyle(color: LU.accent)),
                      ]),
                      style: display(28).copyWith(letterSpacing: -0.5),
                      semanticsLabel: 'Line Up',
                    ),
                  ),
                  CircleIconButton(
                    icon: Icons.person_outline,
                    tooltip: 'Profil',
                    onPressed: () => context.go('/home/profile'),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              if (info != null)
                EnergyBadge(energy: info.energy)
              else if (home.hasError)
                _Tile(
                  icon: Icons.error_outline,
                  iconBg: const Color(0xFFFDE4E4),
                  iconFg: LU.wrong,
                  title: 'Bilgiler yüklenemedi',
                  subtitle: '${home.error}',
                  onTap: () => ref.invalidate(homeProvider),
                )
              else
                const LinearProgressIndicator(),
              if (user.isGuest)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(10),
                    onTap: () => context.go('/home/profile'),
                    child: const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 4, vertical: 6),
                      child: Row(
                        children: [
                          Icon(Icons.info_outline, size: 16, color: LU.muted),
                          SizedBox(width: 6),
                          Expanded(
                            child: Text('Misafir hesap: ilerlemen yalnızca bu cihazda. Kaydetmek için profil.',
                                style: TextStyle(fontSize: 12, color: LU.muted)),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              const SizedBox(height: 14),
              _DailyCard(daily: info?.daily, onTap: info?.daily == null ? null : () => context.go('/home/daily')),
              const SizedBox(height: 14),
              IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(
                      child: _ModeTile(
                        icon: Icons.timeline,
                        iconBg: LU.primarySoft,
                        iconFg: LU.onPrimarySoft,
                        title: 'Zaman Çizgisi',
                        line: timeline != null
                            ? 'Devam eden tur · ${timeline.score} kart'
                            : timelineWins > 0
                                ? '$timelineWins galibiyet'
                                : 'Kartları çizgide sıraya diz',
                        cost: timeline != null ? 'Devam et' : cost,
                        onTap: () => context.go('/home/timeline'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _ModeTile(
                        icon: Icons.swap_vert,
                        iconBg: LU.accentSoft,
                        iconFg: LU.accentText,
                        title: 'Seri',
                        line: streak != null
                            ? 'Devam eden seri · ${streak.score}'
                            : bestStreak > 0
                                ? 'Rekor $bestStreak'
                                : 'Daha büyük mü, küçük mü?',
                        cost: streak != null ? 'Devam et' : cost,
                        onTap: () => context.go('/home/streak'),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              _Tile(
                icon: Icons.compare_arrows,
                iconBg: const Color(0xFFE3F5EA),
                iconFg: const Color(0xFF17773F),
                title: 'Meydan okumalar',
                subtitle: incoming > 0
                    ? 'Sana meydan okuyanlar var · kabul etmek ücretsiz'
                    : 'Arkadaşlarına aynı kartları oynat',
                badge: incoming > 0 ? '$incoming yeni' : null,
                onTap: () async {
                  await context.push('/home/challenges');
                  ref.invalidate(challengeListsProvider);
                },
              ),
              const SizedBox(height: 14),
              _ProTile(active: pro, onTap: () => context.go('/home/pro')),
              const SizedBox(height: 16),
              Center(
                child: TextButton(
                  onPressed: () => ref.invalidate(_healthProvider),
                  child: Text(
                    '${health.when(
                      data: (status) => 'Sunucu: $status',
                      loading: () => 'Sunucu kontrol ediliyor...',
                      error: (error, _) => 'Sunucu: $error',
                    )} · ${Uri.parse(apiBaseUrl).host}',
                    style: const TextStyle(fontSize: 12, color: LU.muted),
                  ),
                ),
              ),
              if (!kReleaseMode)
                Center(
                  child: TextButton.icon(
                    onPressed: () => context.go('/home/dev'),
                    icon: const Icon(Icons.build_outlined, size: 16),
                    label: const Text('Geliştirici araçları', style: TextStyle(fontSize: 12)),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Today's puzzle: the big blue card at the top of the menu.
class _DailyCard extends StatelessWidget {
  const _DailyCard({required this.daily, required this.onTap});

  final DailyHome? daily;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final d = daily;
    final (title, line) = switch (d?.status) {
      null => ('Şu an bulmaca yok', 'Yeterli kart olunca burada görünecek'),
      'new' => ('Bugünün ${d!.cards} kartını sırala', 'Ücretsiz · ${d.maxAttempts} deneme hakkı'),
      'playing' => ('Devam et', '${d!.maxAttempts - d.attemptsUsed} deneme hakkın kaldı'),
      'won' => ('Çözdün!', '${d!.solvedIn}. denemede · sonucu paylaş'),
      _ => ('Bu sefer olmadı', "Yeni bulmaca sabah 07:30'da"),
    };
    const caption = TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600, letterSpacing: 0.6);
    return Material(
      color: d == null ? LU.muted : LU.primary,
      borderRadius: BorderRadius.circular(24),
      child: InkWell(
        borderRadius: BorderRadius.circular(24),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: Text(d == null ? 'GÜNLÜK BULMACA' : 'GÜNLÜK BULMACA #${d.number}', style: caption)),
                  if ((d?.streak ?? 0) > 0)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.18),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.local_fire_department, size: 15, color: Colors.white),
                          const SizedBox(width: 4),
                          Text('${d!.streak} gün', style: caption.copyWith(letterSpacing: 0)),
                        ],
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              Text(title, style: display(26, color: Colors.white)),
              const SizedBox(height: 12),
              ExcludeSemantics(
                child: Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    for (var i = 0; i < (d?.cards ?? 6); i++)
                      Container(
                        width: 36,
                        height: 48,
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: d?.status == 'won' ? 0.85 : 0.22),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: d?.status == 'won' ? const Icon(Icons.check, size: 18, color: LU.right) : null,
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              Text(line, style: TextStyle(color: Colors.white.withValues(alpha: 0.92), fontSize: 14)),
            ],
          ),
        ),
      ),
    );
  }
}

/// A game mode in the two-column row: icon, name, record (or the run being played), cost.
class _ModeTile extends StatelessWidget {
  const _ModeTile({
    required this.icon,
    required this.iconBg,
    required this.iconFg,
    required this.title,
    required this.line,
    required this.cost,
    required this.onTap,
  });

  final IconData icon;
  final Color iconBg;
  final Color iconFg;
  final String title;
  final String line;

  /// "1 enerji" / "Sınırsız" / "Devam et"; null while loading.
  final String? cost;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(color: LU.surface, borderRadius: BorderRadius.circular(20), boxShadow: LU.shadow),
      child: Material(
        type: MaterialType.transparency,
        child: InkWell(
          borderRadius: BorderRadius.circular(20),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(color: iconBg, borderRadius: BorderRadius.circular(12)),
                  child: Icon(icon, color: iconFg, size: 22),
                ),
                const SizedBox(height: 10),
                Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                const SizedBox(height: 2),
                Text(line, maxLines: 2, style: const TextStyle(fontSize: 13, color: LU.muted)),
                const Spacer(),
                if (cost != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(cost!,
                        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: LU.accentText)),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A full-width white row: icon, title, subtitle and an optional red badge.
class _Tile extends StatelessWidget {
  const _Tile({
    required this.icon,
    required this.iconBg,
    required this.iconFg,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.badge,
  });

  final IconData icon;
  final Color iconBg;
  final Color iconFg;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final String? badge;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(color: LU.surface, borderRadius: BorderRadius.circular(20), boxShadow: LU.shadow),
      child: Material(
        type: MaterialType.transparency,
        child: InkWell(
          borderRadius: BorderRadius.circular(20),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            child: Row(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(color: iconBg, borderRadius: BorderRadius.circular(12)),
                  child: Icon(icon, color: iconFg, size: 22),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                      Text(subtitle,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 13, color: LU.muted)),
                    ],
                  ),
                ),
                if (badge != null)
                  Container(
                    margin: const EdgeInsets.only(left: 8),
                    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
                    decoration: BoxDecoration(color: const Color(0xFFD64545), borderRadius: BorderRadius.circular(12)),
                    child: Text(badge!,
                        style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w700)),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Line Up Pro at the bottom: an outlined row (or "active" when the user has it).
class _ProTile extends StatelessWidget {
  const _ProTile({required this.active, required this.onTap});

  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      type: MaterialType.transparency,
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: const Color(0xFFC3C9D6), width: 1.5),
          ),
          child: Row(
            children: [
              const Icon(Icons.workspace_premium, color: LU.accent),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(active ? 'Pro üyeliğin aktif' : 'Line Up Pro',
                        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                    const Text('Sınırsız enerji · reklamsız devam · arşiv',
                        style: TextStyle(fontSize: 13, color: LU.muted)),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: LU.muted),
            ],
          ),
        ),
      ),
    );
  }
}
