import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/models.dart';
import '../../core/providers.dart';

/// Current version of a legal text in a dialog (consent screen, profile).
Future<void> showLegalDocument(BuildContext context, WidgetRef ref, LegalDocument doc) {
  final body = ref.read(authServiceProvider).legalBody(doc.kind);
  return showDialog<void>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(doc.title),
      content: SizedBox(
        width: double.maxFinite,
        child: FutureBuilder<String>(
          future: body,
          builder: (context, snapshot) {
            if (snapshot.hasError) return Text('${snapshot.error}');
            if (!snapshot.hasData) return const Center(heightFactor: 2, child: CircularProgressIndicator());
            // Markdown shown as plain text for now (visual design phase can render it).
            return SingleChildScrollView(child: SelectableText(snapshot.data!));
          },
        ),
      ),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Kapat'))],
    ),
  );
}
