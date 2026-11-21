import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'router.dart';

void main() {
  // ProviderScope holds every Riverpod provider (session, API client, ...).
  runApp(const ProviderScope(child: LineUpApp()));
}

class LineUpApp extends ConsumerWidget {
  const LineUpApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp.router(
      title: 'Line Up',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(colorSchemeSeed: Colors.indigo),
      routerConfig: ref.watch(routerProvider),
    );
  }
}
