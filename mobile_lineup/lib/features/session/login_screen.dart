import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/api_client.dart';
import 'session_controller.dart';

/// Email / username + password. Reached from the consent screen (new device), when a registered account has no
/// session (logged out, frozen, expired), and from the profile of a guest ([fromGuest]).
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key, this.fromGuest = false});

  final bool fromGuest;

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _identifier = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  bool _hidden = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    final session = ref.read(sessionProvider).value;
    if (session is SessionNeedsLogin) _identifier.text = session.identifier;
  }

  @override
  void dispose() {
    _identifier.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    final identifier = _identifier.text.trim();
    if (identifier.isEmpty || _password.text.isEmpty) {
      setState(() => _error = 'E-posta (ya da kullanıcı adı) ve şifreyi gir.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(sessionProvider.notifier).login(identifier, _password.text);
      if (mounted) context.go('/home');
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _startAsGuest() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Misafir olarak başla'),
        content: const Text('Bu cihaz hesabını unutur ve yeni bir misafir hesabı açılır. Hesabın silinmez; '
            'istediğin zaman e-posta ve şifrenle yeniden giriş yapabilirsin.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Vazgeç')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Başla')),
        ],
      ),
    );
    if (ok == true) await ref.read(sessionProvider.notifier).startAsGuest();
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider).value;
    final needsLogin = session is SessionNeedsLogin;
    return Scaffold(
      appBar: AppBar(title: const Text('Giriş yap'), automaticallyImplyLeading: !needsLogin),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(needsLogin
              ? 'Devam etmek için hesabına giriş yap.'
              : 'Kayıtlı hesabınla giriş yaparsan ilerlemen bu cihaza gelir.'),
          if (widget.fromGuest) ...[
            const SizedBox(height: 8),
            Text('Dikkat: bu cihazdaki misafir ilerlemen giriş yaptığın hesaba taşınmaz.',
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ],
          const SizedBox(height: 16),
          TextField(
            controller: _identifier,
            keyboardType: TextInputType.emailAddress,
            autocorrect: false,
            textInputAction: TextInputAction.next,
            decoration: const InputDecoration(labelText: 'E-posta ya da kullanıcı adı', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _password,
            obscureText: _hidden,
            textInputAction: TextInputAction.done,
            onSubmitted: (_) => _busy ? null : _login(),
            decoration: InputDecoration(
              labelText: 'Şifre',
              border: const OutlineInputBorder(),
              suffixIcon: IconButton(
                icon: Icon(_hidden ? Icons.visibility : Icons.visibility_off),
                onPressed: () => setState(() => _hidden = !_hidden),
              ),
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ],
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _busy ? null : _login,
            child: _busy
                ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Giriş yap'),
          ),
          if (needsLogin) ...[
            const SizedBox(height: 24),
            TextButton(onPressed: _busy ? null : _startAsGuest, child: const Text('Misafir olarak yeni başla')),
          ],
        ],
      ),
    );
  }
}
