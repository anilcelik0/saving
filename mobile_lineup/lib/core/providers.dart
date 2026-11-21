import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../features/session/auth_service.dart';
import 'api_client.dart';
import 'token_store.dart';

/// App-wide singletons. Screens read them with `ref.read(...)` / `ref.watch(...)`.
final tokenStoreProvider = Provider<TokenStore>((ref) => TokenStore());

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient(ref.watch(tokenStoreProvider)));

final authServiceProvider = Provider<AuthService>(
  (ref) => AuthService(ref.watch(apiClientProvider), ref.watch(tokenStoreProvider)),
);
