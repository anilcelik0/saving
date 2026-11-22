import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';
import '../home/home_data.dart';
import '../profile/profile_data.dart';

/// Pro: what it gives and its status. Store purchases (RevenueCat, monthly / yearly) are connected before release
/// (Phase 9, needs the Play Console app + RevenueCat project); the server already follows RevenueCat's webhook.
class ProScreen extends ConsumerStatefulWidget {
  const ProScreen({super.key});

  @override
  ConsumerState<ProScreen> createState() => _ProScreenState();
}

class _ProScreenState extends ConsumerState<ProScreen> {
  bool _busy = false;

  /// Debug builds only: the DEBUG-only server endpoint gives / takes Pro without a store.
  Future<void> _devToggle(bool on) async {
    setState(() => _busy = true);
    try {
      await ref.read(apiClientProvider).post('billing/dev/entitlements/', data: {'key': 'pro', 'days': on ? 30 : 0});
      ref.invalidate(homeProvider);
      ref.invalidate(profileProvider);
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final pro = ref.watch(homeProvider).value?.pro;
    final active = pro?.active ?? false;
    final until = pro?.expiresAt;
    Widget benefit(IconData icon, String title, String text) => ListTile(
          contentPadding: EdgeInsets.zero,
          leading: Icon(icon, color: theme.colorScheme.primary),
          title: Text(title),
          subtitle: Text(text),
        );
    return Scaffold(
      appBar: AppBar(title: const Text('Line Up Pro')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            color: active ? theme.colorScheme.primaryContainer : null,
            child: ListTile(
              leading: const Icon(Icons.workspace_premium),
              title: Text(active ? 'Pro üyeliğin aktif' : 'Pro üye değilsin'),
              subtitle: active
                  ? Text(until == null ? 'Süresiz' : 'Bitiş: ${until.day}.${until.month}.${until.year}')
                  : null,
            ),
          ),
          const SizedBox(height: 8),
          benefit(Icons.bolt, 'Sınırsız enerji', 'Zaman Çizgisi ve Seri turları enerji harcamaz.'),
          benefit(Icons.replay, 'Reklamsız devam', 'Can bitince reklam izlemeden bir kez devam et.'),
          benefit(Icons.history, 'Bulmaca arşivi', 'Geçmiş günlerin bulmacalarını çöz.'),
          benefit(Icons.block, 'Reklamsız deneyim', 'Hiçbir zaman zorunlu reklam yok; ödüllü reklama da gerek kalmaz.'),
          const SizedBox(height: 16),
          if (!active) ...[
            const FilledButton(onPressed: null, child: Text('Aylık plan')),
            const SizedBox(height: 8),
            const OutlinedButton(onPressed: null, child: Text('Yıllık plan')),
            const SizedBox(height: 8),
            Text('Satın alma, mağaza bağlantısı kurulunca (yayından önce) açılacak.',
                style: theme.textTheme.bodySmall, textAlign: TextAlign.center),
          ],
          if (!kReleaseMode) ...[
            const Divider(height: 32),
            Text('Geliştirme (yalnızca debug)', style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: _busy ? null : () => _devToggle(!active),
              child: Text(active ? "Pro'yu kapat" : "Pro'yu aç (30 gün)"),
            ),
          ],
        ],
      ),
    );
  }
}
