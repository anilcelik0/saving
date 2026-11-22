import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import 'legal_dialog.dart';
import 'session_controller.dart';

/// Legal texts to accept: before the first guest account, or after a new version is published.
class ConsentScreen extends ConsumerStatefulWidget {
  const ConsentScreen({super.key});

  @override
  ConsumerState<ConsentScreen> createState() => _ConsentScreenState();
}

class _ConsentScreenState extends ConsumerState<ConsentScreen> {
  bool _accepted = false;

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider).value;
    if (session is! SessionNeedsConsent) return const Scaffold();
    return Scaffold(
      appBar: AppBar(title: Text(session.newGuest ? 'Hoş geldin' : 'Güncellenen metinler')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(session.newGuest
              ? 'Oynamaya başlamadan önce aşağıdaki metinleri okuyup onaylaman gerekiyor.'
              : 'Bazı metinler güncellendi. Devam etmek için yeni sürümleri onayla.'),
          const SizedBox(height: 12),
          for (final doc in session.documents)
            Card(
              child: ListTile(
                title: Text(doc.title),
                subtitle: Text('${doc.kindLabel} · sürüm ${doc.version}'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => showLegalDocument(context, ref, doc),
              ),
            ),
          CheckboxListTile(
            value: _accepted,
            onChanged: (value) => setState(() => _accepted = value ?? false),
            title: const Text('Okudum, onaylıyorum'),
            controlAffinity: ListTileControlAffinity.leading,
            contentPadding: EdgeInsets.zero,
          ),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: _accepted ? () => ref.read(sessionProvider.notifier).accept() : null,
            child: const Text('Devam'),
          ),
          if (session.newGuest) ...[
            const SizedBox(height: 16),
            TextButton(
              onPressed: () => context.push('/login'),
              child: const Text('Zaten hesabın var mı? Giriş yap'),
            ),
          ],
        ],
      ),
    );
  }
}
