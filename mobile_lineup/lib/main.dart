import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_mobile_ads/google_mobile_ads.dart';
import 'package:material_ui/material_ui.dart';

import 'router.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Firebase config comes from android/app/google-services.json (Gradle plugin), no Dart options needed.
  await Firebase.initializeApp();
  unawaited(MobileAds.instance.initialize());
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
