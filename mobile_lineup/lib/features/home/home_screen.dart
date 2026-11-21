import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config.dart';
import '../../core/providers.dart';
import '../session/session_controller.dart';

/// Backend health (`/api/v1/health/`), shown on the home screen during development.
final _healthProvider = FutureProvider.autoDispose<String>((ref) async {
  final data = await ref.watch(apiClientProvider).get('health/', auth: false);
  return '${data['status']}';
});

/// Main menu. Game modes arrive in Phases 1-3.
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider).value;
    if (session is! SessionReady) return const Scaffold();
    final user = session.user;
    final health = ref.watch(_healthProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Line Up')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Merhaba, ${user.username}', style: Theme.of(context).textTheme.titleLarge),
          if (user.isGuest) const Text('Misafir hesap · ilerlemen bu cihazda saklanıyor'),
          const SizedBox(height: 24),
          const _ModeTile(icon: Icons.timeline, title: 'Zaman Çizgisi', phase: 1),
          const _ModeTile(icon: Icons.swap_vert, title: 'Seri', phase: 2),
          const _ModeTile(icon: Icons.today, title: 'Günlük Bulmaca', phase: 3),
          const SizedBox(height: 24),
          ListTile(
            dense: true,
            leading: const Icon(Icons.dns_outlined),
            title: Text(apiBaseUrl),
            subtitle: Text(health.when(
              data: (status) => 'Sunucu: $status',
              loading: () => 'Sunucu kontrol ediliyor...',
              error: (error, _) => 'Sunucu: $error',
            )),
            onTap: () => ref.invalidate(_healthProvider),
          ),
        ],
      ),
    );
  }
}

class _ModeTile extends StatelessWidget {
  const _ModeTile({required this.icon, required this.title, required this.phase});

  final IconData icon;
  final String title;
  final int phase;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        enabled: false,
        leading: Icon(icon),
        title: Text(title),
        subtitle: Text('Yakında (Faz $phase)'),
      ),
    );
  }
}
