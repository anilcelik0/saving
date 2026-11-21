import 'package:dio/dio.dart';

import '../config.dart';
import 'token_store.dart';

/// Error shown to the user: the backend's Turkish `detail` (or first field error) + machine-readable `code`.
class ApiException implements Exception {
  ApiException(this.message, {this.code, this.statusCode});

  final String message;
  final String? code;
  final int? statusCode;

  factory ApiException.fromDio(DioException e) {
    final response = e.response;
    if (response == null) {
      return ApiException('Sunucuya ulaşılamadı. İnternet bağlantını kontrol et.', code: 'network');
    }
    final data = response.data;
    if (data is Map) {
      final detail = data['detail'];
      if (detail is String) {
        return ApiException(detail, code: data['code'] as String?, statusCode: response.statusCode);
      }
      // field errors: {"field": ["message", ...]}
      for (final value in data.values) {
        if (value is List && value.isNotEmpty) {
          return ApiException('${value.first}', statusCode: response.statusCode);
        }
      }
    }
    return ApiException('Beklenmeyen bir hata oluştu (${response.statusCode}).', statusCode: response.statusCode);
  }

  @override
  String toString() => message;
}

/// Neither the refresh token nor the stored guest credentials could open a session.
class SessionLostException extends ApiException {
  SessionLostException() : super('Oturum açılamadı.', code: 'session_lost');
}

/// JSON API client: adds the access token, and on a 401 renews the session once
/// (refresh token, else guest re-login) and repeats the request.
class ApiClient {
  ApiClient(this._tokens) {
    final options = BaseOptions(
      baseUrl: '$apiBaseUrl/',
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 20),
      contentType: Headers.jsonContentType,
    );
    _dio = Dio(options)
      ..interceptors.add(QueuedInterceptorsWrapper(onRequest: _onRequest, onError: _onError));
    // Without interceptors: token renewal and the repeated request must not re-enter the queue above.
    _plain = Dio(options);
  }

  final TokenStore _tokens;
  late final Dio _dio;
  late final Dio _plain;

  /// [auth] false = public endpoint (no token, no renewal).
  Future<dynamic> get(String path, {Map<String, dynamic>? query, bool auth = true}) =>
      _send(() => _dio.get(path, queryParameters: query, options: Options(extra: {'auth': auth})));

  Future<dynamic> post(String path, {Object? data, bool auth = true}) =>
      _send(() => _dio.post(path, data: data, options: Options(extra: {'auth': auth})));

  Future<dynamic> _send(Future<Response<dynamic>> Function() call) async {
    try {
      return (await call()).data;
    } on DioException catch (e) {
      final error = e.error;
      if (error is ApiException) throw error;
      throw ApiException.fromDio(e);
    }
  }

  void _onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final access = _tokens.access;
    if (options.extra['auth'] != false && access != null) {
      options.headers['Authorization'] = 'Bearer $access';
    }
    handler.next(options);
  }

  Future<void> _onError(DioException err, ErrorInterceptorHandler handler) async {
    final options = err.requestOptions;
    if (err.response?.statusCode != 401 || options.extra['auth'] == false || options.extra['retried'] == true) {
      return handler.next(err);
    }
    // Requests queued behind a renewal carry the old token: just repeat them with the new one.
    final renewedMeanwhile = _tokens.access != null && options.headers['Authorization'] != 'Bearer ${_tokens.access}';
    try {
      if (!renewedMeanwhile && !await renewSession()) {
        return handler.next(DioException(requestOptions: options, response: err.response, error: SessionLostException()));
      }
      options.headers['Authorization'] = 'Bearer ${_tokens.access}';
      options.extra['retried'] = true;
      handler.resolve(await _plain.fetch(options));
    } on DioException catch (e) {
      handler.next(e);
    }
  }

  /// New tokens from the refresh token, else by logging in with the guest credentials.
  /// Returns false (tokens cleared) when both are refused; network errors are rethrown, nothing is cleared.
  Future<bool> renewSession() async {
    final refresh = _tokens.refresh;
    if (refresh != null) {
      try {
        final r = await _plain.post('auth/refresh/', data: {'refresh': refresh});
        await _tokens.saveTokens(access: r.data['access'], refresh: r.data['refresh'] ?? refresh);
        return true;
      } on DioException catch (e) {
        if (e.response == null) rethrow;
      }
    }
    if (_tokens.hasGuestCredentials) {
      try {
        final r = await _plain.post('auth/login/', data: {
          'app': appSlug,
          'identifier': _tokens.guestUsername,
          'password': _tokens.guestPassword,
        });
        await _tokens.saveTokens(access: r.data['access'], refresh: r.data['refresh']);
        return true;
      } on DioException catch (e) {
        if (e.response == null) rethrow;
      }
    }
    await _tokens.clearTokens();
    return false;
  }
}
