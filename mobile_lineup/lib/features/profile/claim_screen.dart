import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';
import '../session/session_controller.dart';

/// A guest keeps its account by setting an email + password (username optional). Same account, same progress.
class ClaimScreen extends ConsumerStatefulWidget {
  const ClaimScreen({super.key});

  @override
  ConsumerState<ClaimScreen> createState() => _ClaimScreenState();
}

class _ClaimScreenState extends ConsumerState<ClaimScreen> {
  final _username = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _again = TextEditingController();
  bool _busy = false;
  bool _hidden = true;
  String? _error;

  @override
  void dispose() {
    for (final c in [_username, _email, _password, _again]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    final email = _email.text.trim();
    if (!email.contains('@')) return setState(() => _error = 'Geçerli bir e-posta adresi gir.');
    if (_password.text.isEmpty) return setState(() => _error = 'Bir şifre belirle.');
    if (_password.text != _again.text) return setState(() => _error = 'Şifreler aynı değil.');
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final user = await ref.read(authServiceProvider).claim(
            email: email,
            password: _password.text,
            username: _username.text.trim(),
          );
      ref.read(sessionProvider.notifier).updateUser(user);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Hesabın kaydedildi. Artık e-posta ve şifrenle giriş yapabilirsin.')),
      );
      context.pop();
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    InputDecoration field(String label, {String? helper, Widget? suffix}) =>
        InputDecoration(labelText: label, helperText: helper, border: const OutlineInputBorder(), suffixIcon: suffix);
    return Scaffold(
      appBar: AppBar(title: const Text('Hesabını kaydet')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('İlerlemen aynı hesapta kalır. Sonra bu bilgilerle başka cihazda da giriş yapabilirsin.'),
          const SizedBox(height: 16),
          TextField(
            controller: _username,
            autocorrect: false,
            textInputAction: TextInputAction.next,
            decoration: field('Kullanıcı adı (isteğe bağlı)',
                helper: '3-30 karakter: küçük harf, rakam, _ . - · boş bırakırsan şimdiki kalır'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _email,
            keyboardType: TextInputType.emailAddress,
            autocorrect: false,
            textInputAction: TextInputAction.next,
            decoration: field('E-posta'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _password,
            obscureText: _hidden,
            textInputAction: TextInputAction.next,
            decoration: field(
              'Şifre',
              helper: 'En az 8 karakter; çok yaygın ya da sadece rakam olamaz',
              suffix: IconButton(
                icon: Icon(_hidden ? Icons.visibility : Icons.visibility_off),
                onPressed: () => setState(() => _hidden = !_hidden),
              ),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _again,
            obscureText: _hidden,
            textInputAction: TextInputAction.done,
            onSubmitted: (_) => _busy ? null : _save(),
            decoration: field('Şifre (tekrar)'),
          ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ],
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _busy ? null : _save,
            child: _busy
                ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Kaydet'),
          ),
        ],
      ),
    );
  }
}
