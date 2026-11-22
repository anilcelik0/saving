import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/api_client.dart';
import '../../core/models.dart';
import '../../core/providers.dart';
import '../billing/reward_ads.dart';
import '../home/home_data.dart';
import '../notifications/local_notices.dart';
import '../session/legal_dialog.dart';
import '../session/session_controller.dart';
import 'profile_data.dart';

/// Profile: who you are (guest or registered), stats, legal texts, account actions.
class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider).value;
    if (session is! SessionReady) return const Scaffold();
    final user = session.user;
    final stats = ref.watch(profileProvider);
    final docs = ref.watch(legalDocumentsProvider);
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Profil')),
      body: RefreshIndicator(
        onRefresh: () => ref.refresh(profileProvider.future),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const CircleAvatar(child: Icon(Icons.person)),
              title: Text(user.username, style: theme.textTheme.titleMedium),
              subtitle: Text(user.isGuest ? 'Misafir hesap · ilerlemen sadece bu cihazda' : user.email),
            ),
            if (user.isGuest)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Text('Uygulamayı silersen ya da telefon değiştirirsen ilerlemen kaybolur. E-posta ve şifre '
                          'belirleyerek hesabını kaydet; başka cihazda da giriş yapabilirsin.'),
                      const SizedBox(height: 8),
                      FilledButton(
                        onPressed: () => context.push('/home/profile/claim'),
                        child: const Text('Hesabını kaydet'),
                      ),
                      TextButton(
                        onPressed: () => context.push('/home/login'),
                        child: const Text('Kayıtlı hesabınla giriş yap'),
                      ),
                    ],
                  ),
                ),
              ),
            const SizedBox(height: 16),
            Text('İstatistikler', style: theme.textTheme.titleMedium),
            switch (stats) {
              AsyncValue(:final value?) => _Stats(stats: value),
              AsyncValue(hasError: true) => ListTile(
                  leading: const Icon(Icons.error_outline),
                  title: Text('${stats.error}'),
                  trailing: const Icon(Icons.refresh),
                  onTap: () => ref.invalidate(profileProvider),
                ),
              _ => const Padding(padding: EdgeInsets.all(16), child: LinearProgressIndicator()),
            },
            const SizedBox(height: 16),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.workspace_premium),
              title: const Text('Line Up Pro'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => context.push('/home/pro'),
            ),
            const SizedBox(height: 16),
            Text('Yasal metinler', style: theme.textTheme.titleMedium),
            for (final doc in docs.value ?? const <LegalDocument>[])
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.description_outlined),
                title: Text(doc.title),
                subtitle: Text('sürüm ${doc.version}'),
                onTap: () => showLegalDocument(context, ref, doc),
              ),
            const _AdPrivacyTile(),
            const SizedBox(height: 16),
            Text('Bildirimler', style: theme.textTheme.titleMedium),
            const _NoticeSwitch(
              prefKey: LocalNotices.prefEnergy,
              title: 'Enerji dolunca haber ver',
            ),
            const _NoticeSwitch(
              prefKey: LocalNotices.prefDaily,
              title: 'Günlük bulmaca hatırlatması (07:30)',
            ),
            const SizedBox(height: 16),
            Text('Hesap', style: theme.textTheme.titleMedium),
            if (!user.isGuest) ...[
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.logout),
                title: const Text('Çıkış yap'),
                onTap: () => _logout(context, ref),
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.ac_unit),
                title: const Text('Hesabı dondur'),
                subtitle: const Text('Verilerin saklanır; tekrar giriş yapınca yeniden açabilirsin'),
                onTap: () => _accountAction(context, ref, user, delete: false),
              ),
            ],
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(Icons.delete_outline, color: theme.colorScheme.error),
              title: Text('Hesabı sil', style: TextStyle(color: theme.colorScheme.error)),
              subtitle: Text(user.isGuest
                  ? 'Misafir hesabın ve tüm ilerlemen silinir'
                  : 'Bekleme süresi içinde giriş yaparak iptal edebilirsin'),
              onTap: () => _accountAction(context, ref, user, delete: true),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _logout(BuildContext context, WidgetRef ref) async {
    try {
      await ref.read(sessionProvider.notifier).logout();
    } on ApiException catch (e) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  /// Freeze or delete, confirmed with the password (a guest's stored password is sent for it).
  Future<void> _accountAction(BuildContext context, WidgetRef ref, AppUser user, {required bool delete}) async {
    final password = await showDialog<String>(
      context: context,
      builder: (context) => _ConfirmDialog(user: user, delete: delete),
    );
    if (password == null) return;
    final controller = ref.read(sessionProvider.notifier);
    try {
      delete ? await controller.requestDeletion(password) : await controller.deactivate(password);
    } on ApiException catch (e) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }
}

/// On-device reminder on / off (stored on this device).
class _NoticeSwitch extends ConsumerStatefulWidget {
  const _NoticeSwitch({required this.prefKey, required this.title});

  final String prefKey;
  final String title;

  @override
  ConsumerState<_NoticeSwitch> createState() => _NoticeSwitchState();
}

class _NoticeSwitchState extends ConsumerState<_NoticeSwitch> {
  bool? _on;

  @override
  void initState() {
    super.initState();
    ref.read(localNoticesProvider).enabled(widget.prefKey).then((v) {
      if (mounted) setState(() => _on = v);
    });
  }

  Future<void> _set(bool value) async {
    setState(() => _on = value);
    final notices = ref.read(localNoticesProvider);
    await notices.setEnabled(widget.prefKey, value);
    if (widget.prefKey == LocalNotices.prefDaily) {
      await notices.dailyReminder();
    } else {
      final e = ref.read(homeProvider).value?.energy;
      await notices.energyFullIn(value && e != null && !e.unlimited ? e.fullInSeconds : null);
    }
  }

  @override
  Widget build(BuildContext context) => SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: Text(widget.title),
        value: _on ?? true,
        onChanged: _on == null ? null : _set,
      );
}

/// "Reklam gizlilik ayarları": only where Google's consent message applies (EEA / UK), as UMP requires.
class _AdPrivacyTile extends ConsumerWidget {
  const _AdPrivacyTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final required = ref.watch(_adPrivacyRequiredProvider).value ?? false;
    if (!required) return const SizedBox.shrink();
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: const Icon(Icons.privacy_tip_outlined),
      title: const Text('Reklam gizlilik ayarları'),
      onTap: () => ref.read(rewardAdsProvider).showPrivacyOptions(),
    );
  }
}

final _adPrivacyRequiredProvider =
    FutureProvider.autoDispose<bool>((ref) => ref.read(rewardAdsProvider).privacyOptionsRequired());

class _ConfirmDialog extends ConsumerStatefulWidget {
  const _ConfirmDialog({required this.user, required this.delete});

  final AppUser user;
  final bool delete;

  @override
  ConsumerState<_ConfirmDialog> createState() => _ConfirmDialogState();
}

class _ConfirmDialogState extends ConsumerState<_ConfirmDialog> {
  final _password = TextEditingController();

  @override
  void dispose() {
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final guest = widget.user.isGuest;
    final text = widget.delete
        ? (guest
            ? 'Misafir hesabın ve tüm ilerlemen silinecek; bu cihaz yeni bir misafir hesabıyla başlayacak.'
            : 'Hesabın kilitlenir ve bekleme süresinden sonra tüm ilerlemenle birlikte silinir. Bu süre içinde '
                'giriş yaparsan silme iptal edilir.')
        : 'Hesabın dondurulur ve tüm cihazlarda oturumun kapanır. Verilerin saklanır.';
    return AlertDialog(
      title: Text(widget.delete ? 'Hesabı sil' : 'Hesabı dondur'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(text),
          if (!guest) ...[
            const SizedBox(height: 12),
            TextField(
              controller: _password,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'Şifren', border: OutlineInputBorder()),
            ),
          ],
        ],
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Vazgeç')),
        FilledButton(
          style: widget.delete ? FilledButton.styleFrom(backgroundColor: Theme.of(context).colorScheme.error) : null,
          onPressed: () => Navigator.pop(
            context,
            guest ? ref.read(authServiceProvider).guestPassword ?? '' : _password.text,
          ),
          child: Text(widget.delete ? 'Sil' : 'Dondur'),
        ),
      ],
    );
  }
}

class _Stats extends StatelessWidget {
  const _Stats({required this.stats});

  final ProfileStats stats;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final d = stats.dailyDistribution;
    final most = d.values.fold(1, (a, b) => a > b ? a : b);
    Widget row(String label, String value) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(children: [Expanded(child: Text(label)), Text(value, style: theme.textTheme.titleSmall)]),
        );
    Widget bar(String label, int count) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(
            children: [
              SizedBox(width: 72, child: Text(label, style: theme.textTheme.bodySmall)),
              Expanded(
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: FractionallySizedBox(
                    widthFactor: count == 0 ? 0.04 : count / most,
                    child: Container(
                      height: 16,
                      color: label == 'Çözülemedi' ? theme.colorScheme.errorContainer : theme.colorScheme.primary,
                    ),
                  ),
                ),
              ),
              SizedBox(width: 28, child: Text('$count', textAlign: TextAlign.end)),
            ],
          ),
        );
    return Column(
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Günlük Bulmaca', style: theme.textTheme.titleSmall),
                row('Oynanan / çözülen', '${stats.dailyPlayed} / ${stats.dailySolved}'),
                row('Seri (art arda çözülen gün)', '${stats.dailyStreak}'),
                row('En uzun seri', '${stats.dailyBestStreak}'),
                const SizedBox(height: 4),
                for (final n in ['1', '2', '3']) bar('$n. deneme', d[n] ?? 0),
                bar('Çözülemedi', d['fail'] ?? 0),
              ],
            ),
          ),
        ),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Zaman Çizgisi', style: theme.textTheme.titleSmall),
                row('Biten tur / galibiyet', '${stats.timelinePlayed} / ${stats.timelineWins}'),
                row('En çok kart', '${stats.timelineBest}'),
                const Divider(),
                Text('Seri', style: theme.textTheme.titleSmall),
                row('Biten tur', '${stats.streakPlayed}'),
                row('Rekor', '${stats.streakBest}'),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
