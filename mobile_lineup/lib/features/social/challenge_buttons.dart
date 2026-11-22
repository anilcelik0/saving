import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/api_client.dart';
import 'challenge_data.dart';

/// End panel of a finished normal run: share the same deck as a challenge.
class ChallengeFromRunButton extends ConsumerStatefulWidget {
  const ChallengeFromRunButton({super.key, required this.runId});

  final String runId;

  @override
  ConsumerState<ChallengeFromRunButton> createState() => _ChallengeFromRunButtonState();
}

class _ChallengeFromRunButtonState extends ConsumerState<ChallengeFromRunButton> {
  bool _busy = false;

  Future<void> _create() async {
    setState(() => _busy = true);
    try {
      final challenge = await ref.read(socialApiProvider).create(widget.runId);
      if (mounted) context.push('/home/challenges/${challenge.code}');
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => FilledButton.tonalIcon(
        onPressed: _busy ? null : _create,
        icon: _busy
            ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
            : const Icon(Icons.sports_kabaddi),
        label: const Text('Arkadaşına meydan oku'),
      );
}
