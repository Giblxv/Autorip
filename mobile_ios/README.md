# AutoRIP Mobile para iOS

Cliente Flutter para iPhone/iPad que reproduz o fluxo do app Android: informa o servidor AutoRIP, guarda até cinco endereços recentes localmente e abre o painel no WebView nativo do sistema. O aplicativo não contém nem executa o motor RIP; o processamento permanece no computador servidor, como no [cliente Android existente](../mobile/README.md).

O deployment target iOS deste projeto está em 15.0.

O painel usa `webview_flutter`, que apresenta `WKWebView` no iOS, e `shared_preferences` para uma lista pequena de endereços, nunca para guardar senhas. [Documentação do WebView Flutter](https://pub.dev/packages/webview_flutter) [Documentação de shared_preferences](https://pub.dev/packages/shared_preferences)

## Rodar e testar

Instale Flutter stable em um Mac com Xcode e CocoaPods. A partir desta pasta, rode:

```sh
flutter pub get
flutter analyze
flutter test
flutter run -d <dispositivo-ios>
```

Para criar uma build iOS de distribuição, use `flutter build ipa --release` no macOS e configure uma equipe de assinatura Apple no projeto Xcode. Este ambiente Linux permite validar o código Dart, mas não contém Xcode nem pode assinar ou gerar um IPA.

## Conectar ao AutoRIP

Na primeira abertura, informe o endereço do servidor, por exemplo `http://192.168.1.50:8765`. O host deve permitir conexões da rede local; o servidor AutoRIP mantém autenticação e configuração explícita de bind/hosts. Para acesso externo, use HTTPS e VPN/rede privada. Não publique a porta HTTP diretamente na internet.

O botão **Escanear QR code** pode preencher e abrir o endereço de conexão mostrado no painel. Ele valida a URL antes de conectar e não lê nem salva senhas; o histórico local continua limitado a cinco endereços. Se a câmera não puder ser usada, digite o endereço manualmente ou habilite a permissão de câmera nos Ajustes do iPhone.

Por segurança, o app aceita HTTP somente para localhost, nomes locais (`.local` ou nome sem ponto) e intervalos IPv4/IPv6 privados ou de link-local. Endereços públicos exigem HTTPS. A política ATS do iOS configura exceções HTTP apenas para esses intervalos, sem desativar globalmente o App Transport Security. A lista corresponde às exceções de IP/CIDR que a Apple documenta para ATS no iOS 17+. [ATS: NSExceptionDomains](https://developer.apple.com/documentation/bundleresources/information-property-list/nsapptransportsecurity/nsexceptiondomains) [ATS: NSAllowsLocalNetworking](https://developer.apple.com/documentation/bundleresources/information-property-list/nsapptransportsecurity/nsallowslocalnetworking)

O `Info.plist` inclui uma descrição para o uso da rede local. O app não faz descoberta Bonjour nem tráfego multicast. A Apple documenta as regras do aviso de privacidade local e observa que requisições originadas de `WKWebView` são isentas do privilégio de rede local. [Apple TN3179: privacidade de rede local](https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy)
