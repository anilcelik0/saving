import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';
import '../timeline/timeline_models.dart';

/// "Hata bildir" for a card: shared support API, related object `lineup.card` (the server stores a card snapshot).
Future<void> showCardReportDialog(BuildContext context, WidgetRef ref, GameCard card, {String screen = ''}) async {
  final sent = await showDialog<bool>(
    context: context,
    builder: (context) => _CardReportDialog(card: card, screen: screen),
  );
  if (sent == true && context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Teşekkürler, bildirimin alındı.'), behavior: SnackBarBehavior.floating),
    );
  }
}

class _CardReportDialog extends ConsumerStatefulWidget {
  const _CardReportDialog({required this.card, required this.screen});

  final GameCard card;
  final String screen;

  @override
  ConsumerState<_CardReportDialog> createState() => _CardReportDialogState();
}

class _CardReportDialogState extends ConsumerState<_CardReportDialog> {
  final _message = TextEditingController();
  bool _sending = false;
  String? _error;

  @override
  void dispose() {
    _message.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      await ref.read(apiClientProvider).post('support/issues/', data: {
        'category': 'bug',
        'message': _message.text.trim(),
        'related_type': 'lineup.card',
        'related_id': widget.card.id,
        'context': {'screen': widget.screen, 'card_value': widget.card.value ?? ''},
      });
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      setState(() {
        _sending = false;
        _error = e.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final card = widget.card;
    return AlertDialog(
      title: const Text('Kartta hata bildir'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${card.emoji} ${card.title}${card.value != null ? ' · ${card.value}' : ''}'),
          const SizedBox(height: 12),
          TextField(
            controller: _message,
            autofocus: true,
            maxLines: 3,
            decoration: InputDecoration(
              hintText: 'Ne yanlış? (ör. yıl 1999 değil 2001)',
              errorText: _error,
              border: const OutlineInputBorder(),
            ),
          ),
        ],
      ),
      actions: [
        TextButton(onPressed: _sending ? null : () => Navigator.pop(context, false), child: const Text('Vazgeç')),
        FilledButton(onPressed: _sending ? null : _send, child: const Text('Gönder')),
      ],
    );
  }
}
