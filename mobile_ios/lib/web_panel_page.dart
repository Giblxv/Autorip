import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

import 'server_address.dart';

class WebPanelPage extends StatefulWidget {
  const WebPanelPage({super.key, required this.address});

  final ServerAddress address;

  @override
  State<WebPanelPage> createState() => _WebPanelPageState();
}

class _WebPanelPageState extends State<WebPanelPage> {
  late final WebViewController _controller;
  int _progress = 0;
  bool _loading = true;
  String? _mainFrameError;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(Colors.white)
      ..setNavigationDelegate(
        NavigationDelegate(
          onProgress: (progress) {
            if (mounted) setState(() => _progress = progress);
          },
          onPageStarted: (_) {
            if (!mounted) return;
            setState(() {
              _loading = true;
              _mainFrameError = null;
              _progress = 0;
            });
          },
          onPageFinished: (_) {
            if (!mounted) return;
            setState(() {
              _loading = false;
              _progress = 100;
            });
          },
          onWebResourceError: (error) {
            if (error.isForMainFrame != true || !mounted) return;
            setState(() {
              _loading = false;
              _mainFrameError = 'Não foi possível abrir o servidor. Confira o endereço, o Wi-Fi e se o painel AutoRIP está ativo.';
            });
          },
          onNavigationRequest: (request) {
            final uri = Uri.tryParse(request.url);
            if (uri == null || !{'http', 'https'}.contains(uri.scheme)) {
              return NavigationDecision.prevent;
            }
            return NavigationDecision.navigate;
          },
        ),
      )
      ..loadRequest(widget.address.panelUri);
  }

  Future<void> _goBack() async {
    if (await _controller.canGoBack()) {
      await _controller.goBack();
      return;
    }
    if (mounted) Navigator.of(context).pop();
  }

  Future<void> _reload() async {
    setState(() {
      _mainFrameError = null;
      _loading = true;
      _progress = 0;
    });
    await _controller.reload();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      leading: IconButton(
        tooltip: 'Voltar',
        onPressed: _goBack,
        icon: const Icon(Icons.arrow_back),
      ),
      title: const Text('AutoRIP'),
      actions: <Widget>[
        IconButton(
          tooltip: 'Recarregar painel',
          onPressed: _reload,
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: SafeArea(
      top: false,
      child: Stack(
        children: <Widget>[
          WebViewWidget(controller: _controller),
          if (_loading)
            Align(
              alignment: Alignment.topCenter,
              child: LinearProgressIndicator(
                value: _progress > 0 && _progress < 100
                    ? _progress / 100
                    : null,
                minHeight: 3,
                color: const Color(0xFF00AEEF),
                backgroundColor: const Color(0xFFE7E7E7),
              ),
            ),
          if (_mainFrameError != null)
            Positioned.fill(
              child: ColoredBox(
                color: const Color(0xFFFFF8E1),
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(28),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        const Icon(
                          Icons.wifi_off,
                          size: 48,
                          color: Color(0xFFEC008C),
                        ),
                        const SizedBox(height: 16),
                        const Text(
                          'Falha na conexão',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(_mainFrameError!, textAlign: TextAlign.center),
                        const SizedBox(height: 18),
                        FilledButton.icon(
                          onPressed: _reload,
                          icon: const Icon(Icons.refresh),
                          label: const Text('Tentar novamente'),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    ),
  );
}
