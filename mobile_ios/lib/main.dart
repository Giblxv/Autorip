import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'server_address.dart';
import 'web_panel_page.dart';

const _ink = Color(0xFF1A1A1A);
const _cyan = Color(0xFF00AEEF);
const _pink = Color(0xFFEC008C);
const _yellow = Color(0xFFFFD800);
const _paper = Color(0xFFFFF8E1);

void main() => runApp(const AutoRipApp());

abstract interface class RecentServerStore {
  Future<List<String>> load();
  Future<void> save(List<String> values);
}

class PreferencesRecentServerStore implements RecentServerStore {
  static const _key = 'autorip.server.urls';
  final SharedPreferencesAsync _preferences = SharedPreferencesAsync();

  @override
  Future<List<String>> load() async =>
      await _preferences.getStringList(_key) ?? <String>[];

  @override
  Future<void> save(List<String> values) =>
      _preferences.setStringList(_key, values);
}

@visibleForTesting
class MemoryRecentServerStore implements RecentServerStore {
  MemoryRecentServerStore([List<String> initial = const <String>[]])
    : values = List<String>.of(initial);

  List<String> values;

  @override
  Future<List<String>> load() async => List<String>.of(values);

  @override
  Future<void> save(List<String> next) async {
    values = List<String>.of(next);
  }
}

class AutoRipApp extends StatelessWidget {
  const AutoRipApp({super.key, this.store});

  final RecentServerStore? store;

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'AutoRIP Mobile',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(seedColor: _cyan),
      scaffoldBackgroundColor: const Color(0xFF17131F),
      appBarTheme: const AppBarTheme(
        backgroundColor: Color(0xFF17131F),
        foregroundColor: Colors.white,
        centerTitle: false,
      ),
    ),
    home: ConnectScreen(store: store ?? PreferencesRecentServerStore()),
  );
}

class ConnectScreen extends StatefulWidget {
  const ConnectScreen({super.key, required this.store});

  final RecentServerStore store;

  @override
  State<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends State<ConnectScreen> {
  final TextEditingController _addressController = TextEditingController();
  List<String> _recent = <String>[];
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _loadRecent();
  }

  @override
  void dispose() {
    _addressController.dispose();
    super.dispose();
  }

  Future<void> _loadRecent() async {
    try {
      final saved = await widget.store.load();
      final valid = <String>[];
      for (final entry in saved) {
        final address = ServerAddress.tryParse(entry);
        if (address != null && !valid.contains(address.value)) {
          valid.add(address.value);
        }
      }
      if (!mounted) return;
      setState(() => _recent = valid.take(RecentServers.limit).toList());
    } catch (_) {
      // Local history is optional; the user can still enter an address.
    }
  }

  Future<void> _connect([String? value]) async {
    if (_loading) return;
    final raw = value ?? _addressController.text;
    final message = ServerAddress.validationError(raw);
    if (message != null) {
      setState(() => _error = message);
      return;
    }

    final address = ServerAddress.tryParse(raw)!;
    setState(() {
      _error = null;
      _loading = true;
    });
    final updated = RecentServers.promote(_recent, address.value);
    try {
      await widget.store.save(updated);
      _recent = updated;
    } catch (_) {
      // A preferences write must not prevent opening the server.
    }
    if (!mounted) return;
    setState(() => _loading = false);
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(builder: (_) => WebPanelPage(address: address)),
    );
  }

  Future<void> _scanQr() async {
    if (_loading) return;
    final scannedAddress = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(builder: (_) => const QrScannerPage()),
    );
    if (!mounted || scannedAddress == null) return;
    _addressController.text = scannedAddress;
    await _connect(scannedAddress);
  }

  Future<void> _removeRecent(String value) async {
    final updated = _recent.where((item) => item != value).toList();
    setState(() => _recent = updated);
    try {
      await widget.store.save(updated);
    } catch (_) {
      // Keep the current screen responsive if local storage is unavailable.
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(22),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: _paper,
                border: Border.all(color: _ink, width: 3),
                borderRadius: BorderRadius.circular(22),
                boxShadow: const <BoxShadow>[
                  BoxShadow(color: _pink, offset: Offset(7, 7)),
                ],
              ),
              child: Padding(
                padding: const EdgeInsets.all(22),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    const _BrandTitle(),
                    const SizedBox(height: 8),
                    Text(
                      'Conecte o aplicativo ao painel AutoRIP executando no servidor interno.',
                      style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                        color: const Color(0xFF49434E),
                        height: 1.45,
                      ),
                    ),
                    const SizedBox(height: 26),
                    TextField(
                      controller: _addressController,
                      keyboardType: TextInputType.url,
                      textInputAction: TextInputAction.go,
                      autocorrect: false,
                      enableSuggestions: false,
                      onSubmitted: (_) => _connect(),
                      decoration: InputDecoration(
                        labelText: 'Endereço do servidor',
                        hintText: 'http://192.168.1.50:8765',
                        errorText: _error,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: _ink, width: 2),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: _ink, width: 2),
                        ),
                      ),
                    ),
                    const SizedBox(height: 14),
                    OutlinedButton.icon(
                      onPressed: _loading ? null : _scanQr,
                      icon: const Icon(Icons.qr_code_scanner),
                      label: const Text('Escanear QR code'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: _ink,
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        side: const BorderSide(color: _ink, width: 2),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                    FilledButton.icon(
                      onPressed: _loading ? null : () => _connect(),
                      icon: _loading
                          ? const SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.link),
                      label: Text(_loading ? 'Conectando…' : 'Conectar'),
                      style: FilledButton.styleFrom(
                        backgroundColor: _yellow,
                        foregroundColor: _ink,
                        padding: const EdgeInsets.symmetric(vertical: 15),
                        textStyle: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                        ),
                        side: const BorderSide(color: _ink, width: 2),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                    ),
                    const SizedBox(height: 14),
                    Text(
                      'Use HTTPS para acesso pela internet. Endereços HTTP só são aceitos para a rede local. Configure AUTORIP_BIND_HOST e AUTORIP_ALLOWED_HOSTS no servidor.',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: const Color(0xFF5F5863),
                        height: 1.45,
                      ),
                    ),
                    if (_recent.isNotEmpty) ...<Widget>[
                      const SizedBox(height: 28),
                      Text(
                        'Endereços recentes',
                        style: Theme.of(context).textTheme.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 8),
                      for (final server in _recent)
                        Card(
                          margin: const EdgeInsets.symmetric(vertical: 4),
                          color: Colors.white,
                          child: ListTile(
                            contentPadding: const EdgeInsets.only(left: 12),
                            title: Text(
                              server,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontSize: 14),
                            ),
                            onTap: _loading ? null : () => _connect(server),
                            trailing: IconButton(
                              tooltip: 'Remover endereço recente',
                              onPressed: () => _removeRecent(server),
                              icon: const Icon(Icons.close),
                            ),
                          ),
                        ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
}

class QrScannerPage extends StatefulWidget {
  const QrScannerPage({super.key});

  @override
  State<QrScannerPage> createState() => _QrScannerPageState();
}

class _QrScannerPageState extends State<QrScannerPage> {
  String? _scanError;
  bool _completed = false;

  void _onDetect(BarcodeCapture capture) {
    if (_completed) return;
    for (final barcode in capture.barcodes) {
      final rawValue = barcode.rawValue;
      if (rawValue == null || rawValue.isEmpty) continue;
      final address = ServerAddress.tryParse(rawValue);
      if (address != null) {
        _completed = true;
        Navigator.of(context).pop(address.value);
        return;
      }
      if (_scanError == null) {
        setState(() {
          _scanError = 'QR inválido. Use um endereço HTTP(S) sem usuário, senha, query ou fragmento.';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Escanear QR code'),
      leading: IconButton(
        tooltip: 'Cancelar leitura',
        onPressed: () => Navigator.of(context).pop(),
        icon: const Icon(Icons.close),
      ),
    ),
    body: Stack(
      fit: StackFit.expand,
      children: <Widget>[
        MobileScanner(
          onDetect: _onDetect,
          errorBuilder: (context, error) => ColoredBox(
            color: Colors.black,
            child: Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  'Não foi possível acessar a câmera. Verifique a permissão da câmera nos Ajustes e tente novamente.',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyLarge
                      ?.copyWith(color: Colors.white),
                ),
              ),
            ),
          ),
        ),
        IgnorePointer(
          child: Center(
            child: Container(
              width: 250,
              height: 190,
              decoration: BoxDecoration(
                border: Border.all(color: Colors.white, width: 3),
                borderRadius: BorderRadius.circular(18),
              ),
            ),
          ),
        ),
        Align(
          alignment: Alignment.bottomCenter,
          child: SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Text(
                _scanError ??
                    'Aponte a câmera para o QR code do painel AutoRIP.',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  shadows: <Shadow>[Shadow(color: Colors.black, blurRadius: 8)],
                ),
              ),
            ),
          ),
        ),
      ],
    ),
  );
}

class _BrandTitle extends StatelessWidget {
  const _BrandTitle();

  @override
  Widget build(BuildContext context) => Semantics(
    label: 'AutoRIP',
    header: true,
    child: ExcludeSemantics(
      child: RichText(
        text: const TextSpan(
          style: TextStyle(
            color: _ink,
            fontSize: 48,
            fontWeight: FontWeight.w900,
            letterSpacing: -2,
          ),
          children: <InlineSpan>[
            TextSpan(
              text: 'A',
              style: TextStyle(color: _cyan),
            ),
            TextSpan(
              text: 'u',
              style: TextStyle(color: _pink),
            ),
            TextSpan(
              text: 'to',
              style: TextStyle(
                color: _yellow,
                shadows: <Shadow>[Shadow(color: _ink, offset: Offset(1, 1))],
              ),
            ),
            TextSpan(text: 'RIP'),
          ],
        ),
      ),
    ),
  );
}
