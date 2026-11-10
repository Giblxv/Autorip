import 'package:flutter_test/flutter_test.dart';
import 'package:autorip_mobile_ios/server_address.dart';

void main() {
  group('ServerAddress', () {
    test('normalizes a private IPv4 HTTP address for the panel root', () {
      final address = ServerAddress.tryParse('  http://192.168.1.50:8765/  ');

      expect(address, isNotNull);
      expect(address!.value, 'http://192.168.1.50:8765');
      expect(address.panelUri.toString(), 'http://192.168.1.50:8765/');
    });

    test('accepts local names and private IPv6 over HTTP', () {
      expect(ServerAddress.tryParse('http://autorip.local:8765'), isNotNull);
      expect(ServerAddress.tryParse('http://autorip:8765'), isNotNull);
      expect(ServerAddress.tryParse('http://[fd00::10]:8765'), isNotNull);
      expect(ServerAddress.tryParse('http://169.254.10.20:8765'), isNotNull);
      expect(ServerAddress.tryParse('http://100.64.0.1:8765'), isNull);
    });

    test('accepts public servers over HTTPS', () {
      expect(ServerAddress.tryParse('https://rip.example.com'), isNotNull);
    });

    test('rejects public hosts over unencrypted HTTP', () {
      expect(
        ServerAddress.validationError('http://198.51.100.20:8765'),
        contains('HTTPS'),
      );
      expect(
        ServerAddress.validationError('http://autorip.example.com:8765'),
        contains('HTTPS'),
      );
    });

    test('rejects credentials, query, fragment and unsupported schemes', () {
      for (final value in <String>[
        'http://user:pass@192.168.1.50:8765',
        'http://192.168.1.50:8765/?token=x',
        'http://192.168.1.50:8765/#panel',
        'ftp://192.168.1.50:8765',
        'not a server',
      ]) {
        expect(ServerAddress.tryParse(value), isNull, reason: value);
      }
    });
  });

  test('promotes a server, removes duplicates and keeps only five entries', () {
    final updated = RecentServers.promote(<String>[
      'https://one.example',
      'https://two.example',
      'https://three.example',
      'https://four.example',
      'https://five.example',
    ], 'https://three.example');

    expect(updated, <String>[
      'https://three.example',
      'https://one.example',
      'https://two.example',
      'https://four.example',
      'https://five.example',
    ]);
    expect(updated, hasLength(RecentServers.limit));
  });
}
