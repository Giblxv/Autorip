import 'dart:io';

/// Validated server address accepted by the mobile client.
class ServerAddress {
  const ServerAddress._(this.value);

  /// Address normalized for display and persistence, without a trailing slash.
  final String value;

  /// Root URI loaded by the embedded AutoRIP panel.
  Uri get panelUri => Uri.parse('$value/');

  static const _invalidMessage =
      'Informe um endereço HTTP(S) válido, sem usuário, senha, query ou fragmento.';
  static const _insecureRemoteMessage =
      'HTTP sem criptografia só é permitido na rede local. Para acesso externo, use HTTPS.';

  static String? validationError(String input) {
    final uri = Uri.tryParse(input.trim());
    if (uri == null ||
        !uri.hasScheme ||
        !uri.hasAuthority ||
        uri.host.isEmpty ||
        !{'http', 'https'}.contains(uri.scheme.toLowerCase()) ||
        uri.authority.contains('@') ||
        uri.hasQuery ||
        uri.hasFragment) {
      return _invalidMessage;
    }

    if (uri.scheme.toLowerCase() == 'http' && !_isLocalHost(uri.host)) {
      return _insecureRemoteMessage;
    }
    return null;
  }

  static ServerAddress? tryParse(String input) {
    if (validationError(input) != null) return null;
    final uri = Uri.parse(input.trim());
    final normalized = uri
        .replace(scheme: uri.scheme.toLowerCase())
        .toString()
        .replaceFirst(RegExp(r'/+$'), '');
    return ServerAddress._(normalized);
  }

  static bool _isLocalHost(String host) {
    final address = InternetAddress.tryParse(host);
    if (address != null) {
      final bytes = address.rawAddress;
      if (address.type == InternetAddressType.IPv4) {
        final a = bytes[0];
        final b = bytes[1];
        return a == 10 ||
            (a == 172 && b >= 16 && b <= 31) ||
            (a == 192 && b == 168) ||
            (a == 127) ||
            (a == 169 && b == 254);
      }

      final isLoopback =
          bytes.take(15).every((byte) => byte == 0) && bytes[15] == 1;
      final isUniqueLocal = (bytes[0] & 0xfe) == 0xfc; // fc00::/7
      final isLinkLocal =
          bytes[0] == 0xfe && (bytes[1] & 0xc0) == 0x80; // fe80::/10
      return isLoopback || isUniqueLocal || isLinkLocal;
    }

    final normalizedHost = host.toLowerCase().replaceFirst(RegExp(r'\.$'), '');
    return normalizedHost == 'localhost' ||
        normalizedHost.endsWith('.local') ||
        !normalizedHost.contains('.');
  }
}

/// Pure list operation shared by persistence and tests.
class RecentServers {
  static const limit = 5;

  static List<String> promote(Iterable<String> existing, String value) =>
      <String>{
        value,
        ...existing.where((item) => item != value),
      }.take(limit).toList(growable: false);
}
