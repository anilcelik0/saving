import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/api_client.dart';
import 'session_controller.dart';

/// The account is frozen or waiting for deletion: the game APIs are closed until it is reopened.
class InactiveScreen extends ConsumerStatefulWidget {
  const InactiveScreen({super.key});

  @override
  ConsumerState<InactiveScreen> createState() => _InactiveScreenState();
}

class _InactiveScreenState extends ConsumerState<InactiveScreen> {
  bool _busy = false;

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider).value;
    if (session is! SessionInactive) return const Scaffold();
    final user = session.user;
    final controller = ref.read(sessionProvider.notifier);
    final d = user.deleteAfter;
    final text = user.accountStatus == 'deletion_pending'
        ? 'Hesabın silinmeyi bekliyor${d == null ? '' : ' (${d.day}.${d.month}.${d.year} tarihinde silinecek)'}. '
            'Yeniden açarsan silme iptal edilir ve ilerlemen korunur.'
        : 'Hesabın dondurulmuş. Yeniden açarsan kaldığın yerden devam edersin.';
    return Scaffold(
      appBar: AppBar(title: Text(user.username), automaticallyImplyLeading: false),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(text),
          const SizedBox(height: 24),
          FilledButton(
            onPressed: _busy ? null : () => _run(controller.reactivate),
            child: const Text('Hesabımı yeniden aç'),
          ),
          const SizedBox(height: 8),
          OutlinedButton(onPressed: _busy ? null : () => _run(controller.logout), child: const Text('Çıkış yap')),
        ],
      ),
    );
  }
}
