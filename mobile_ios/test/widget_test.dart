import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:autorip_mobile_ios/main.dart';

void main() {
  testWidgets('shows the AutoRIP connection form and local-network guidance', (
    tester,
  ) async {
    final store = MemoryRecentServerStore();
    await tester.pumpWidget(AutoRipApp(store: store));
    await tester.pumpAndSettle();

    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is RichText && widget.text.toPlainText() == 'AutoRIP',
      ),
      findsOneWidget,
    );
    expect(find.text('Endereço do servidor'), findsOneWidget);
    expect(find.text('Conectar'), findsOneWidget);
    expect(
      find.textContaining('Endereços HTTP só são aceitos para a rede local.'),
      findsOneWidget,
    );
  });

  testWidgets('rejects a public HTTP address before opening the panel', (
    tester,
  ) async {
    final store = MemoryRecentServerStore();
    await tester.pumpWidget(AutoRipApp(store: store));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byType(TextField),
      'http://autorip.example.com:8765',
    );
    await tester.tap(find.text('Conectar'));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('Para acesso externo, use HTTPS.'),
      findsOneWidget,
    );
    expect(store.values, isEmpty);
  });

  testWidgets('opens QR scanner and cancellation preserves manual connection', (
    tester,
  ) async {
    final store = MemoryRecentServerStore();
    await tester.pumpWidget(AutoRipApp(store: store));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Escanear QR code'));
    await tester.pumpAndSettle();

    expect(
      find.text('Aponte a câmera para o QR code do painel AutoRIP.'),
      findsOneWidget,
    );
    expect(find.byTooltip('Cancelar leitura'), findsOneWidget);
    await tester.tap(find.byTooltip('Cancelar leitura'));
    await tester.pumpAndSettle();

    expect(find.text('Endereço do servidor'), findsOneWidget);
    expect(find.text('Conectar'), findsOneWidget);
    expect(store.values, isEmpty);
  });
}
