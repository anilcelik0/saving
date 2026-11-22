import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../config.dart';
import '../../core/providers.dart';
import '../session/session_controller.dart';
import 'energy_widgets.dart';
import 'home_data.dart';

/// Backend health (`/api/v1/health/`), shown on the home screen during development.
final _healthProvider = FutureProvider.autoDispose<String>((ref) async {
  final data = await ref.watch(apiClientProvider).get('health/', auth: false);
  return '${data['status']}';
});

/// Main menu: energy, game modes (resume a run being played), records.
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider).value;
    if (session is! SessionReady) return const Scaffold();
    final user = session.user;
    final health = ref.watch(_healthProvider);
    final home = ref.watch(homeProvider);
    final info = home.value;
    final timeline = info?.playing['timeline'];
    final streak = info?.playing['streak'];
    return Scaffold(
      appBar: AppBar(
        title: const Text('Line Up'),
        actions: [
          IconButton(
            icon: const Icon(Icons.account_circle_outlined),
            tooltip: 'Profil',
            onPressed: () => context.go('/home/profile'),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.refresh(homeProvider.future),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text('Merhaba, ${user.username}', style: Theme.of(context).textTheme.titleLarge),
            if (user.isGuest)
              InkWell(
                onTap: () => context.go('/home/profile'),
                child: const Text('Misafir hesap · ilerlemen bu cihazda saklanıyor · Profil > Hesabını kaydet'),
              ),
            const SizedBox(height: 16),
            if (info != null)
              EnergyBadge(energy: info.energy)
            else if (home.hasError)
              ListTile(
                leading: const Icon(Icons.error_outline),
                title: Text('${home.error}'),
                trailing: const Icon(Icons.refresh),
                onTap: () => ref.invalidate(homeProvider),
              )
            else
              const LinearProgressIndicator(),
            const SizedBox(height: 8),
            _ModeTile(
              icon: Icons.timeline,
              title: 'Zaman Çizgisi',
              subtitle: timeline != null
                  ? 'Devam eden tur · ${timeline.score} kart'
                  : 'Kartları çizgide doğru yere yerleştir · ⚡1'
                        '${(info?.timelineWins ?? 0) > 0 ? ' · ${info!.timelineWins} galibiyet' : ''}',
              onTap: () => context.go('/home/timeline'),
            ),
            _ModeTile(
              icon: Icons.swap_vert,
              title: 'Seri',
              subtitle: streak != null
                  ? 'Devam eden seri · ${streak.score}'
                  : 'Daha büyük mü, küçük mü? · ⚡1'
                        '${(info?.bestStreak ?? 0) > 0 ? ' · rekor ${info!.bestStreak}' : ''}',
              onTap: () => context.go('/home/streak'),
            ),
            _ModeTile(
              icon: Icons.today,
              title: info?.daily == null ? 'Günlük Bulmaca' : 'Günlük Bulmaca #${info!.daily!.number}',
              subtitle: _dailySubtitle(info?.daily),
              onTap: info?.daily == null ? null : () => context.go('/home/daily'),
            ),
            const SizedBox(height: 24),
            ListTile(
              dense: true,
              leading: const Icon(Icons.dns_outlined),
              title: Text(apiBaseUrl),
              subtitle: Text(
                health.when(
                  data: (status) => 'Sunucu: $status',
                  loading: () => 'Sunucu kontrol ediliyor...',
                  error: (error, _) => 'Sunucu: $error',
                ),
              ),
              onTap: () => ref.invalidate(_healthProvider),
            ),
            if (!kReleaseMode)
              ListTile(
                dense: true,
                leading: const Icon(Icons.build_outlined),
                title: const Text('Geliştirici araçları'),
                subtitle: const Text('Test reklamı, push bildirimi'),
                onTap: () => context.go('/home/dev'),
              ),
          ],
        ),
      ),
    );
  }
}

String _dailySubtitle(DailyHome? daily) =>
    _dailyStatus(daily) + ((daily?.streak ?? 0) > 0 ? ' · 🔥 ${daily!.streak} gün' : '');

String _dailyStatus(DailyHome? daily) => switch (daily?.status) {
      null => 'Şu an bulmaca yok',
      'new' => 'Bugünün kartlarını sırala · ücretsiz',
      'playing' => 'Devam et · ${3 - daily!.attemptsUsed} deneme hakkın kaldı',
      'won' => '${daily!.solvedIn}. denemede çözdün · sonucu paylaş',
      _ => "Çözülemedi · yeni bulmaca sabah 07:30'da",
    };

class _ModeTile extends StatelessWidget {
  const _ModeTile({required this.icon, required this.title, required this.subtitle, this.onTap});

  final IconData icon;
  final String title;
  final String subtitle;

  /// null = not available yet
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        enabled: onTap != null,
        leading: Icon(icon),
        title: Text(title),
        subtitle: Text(subtitle),
        trailing: onTap != null ? const Icon(Icons.chevron_right) : null,
        onTap: onTap,
      ),
    );
  }
}
