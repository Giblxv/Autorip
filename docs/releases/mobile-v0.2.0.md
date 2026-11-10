# AutoRIP Mobile 0.2.0 (prévia)

Esta versão é para validação técnica; não é uma publicação da Google Play ou da App Store.

## APKs

- `AutoRIP-Mobile-debug.apk`: cliente Android padrão. É assinado com a chave debug do runner; se o Android recusar uma atualização sobre uma versão anterior, desinstale a prévia antiga antes de instalar esta. Isso pode apagar os endereços recentes guardados localmente.
- `AutoRIP-Mobile-optimized.apk`: build R8 com remoção de recursos. É assinado com chave debug e usa o identificador `com.giblxv.autorip.optimized`, portanto instala como aplicativo separado. Serve para teste/comparação e não substitui o APK de produção.
- `SHA256SUMS.txt`: checksums dos dois APKs.

O servidor AutoRIP continua executando o RIP no computador. O app acessa o painel pela LAN, valida o endereço e pode ler o QR de conexão gerado pelo painel. Senhas não são incluídas nem armazenadas pelo app. Mantenha o servidor restrito à rede privada; não encaminhe a porta HTTP para a internet.

## iOS

O código Flutter e o leitor QR estão no repositório, mas não há IPA assinado ou distribuição TestFlight/App Store. Para testar, é necessário macOS/Xcode e uma equipe de assinatura Apple; consulte o [guia de aplicativos móveis](../GUIA-APPS-MOVEIS.md).

## Verificação

Os APKs são compilados por GitHub Actions. A distribuição está marcada como prévia porque a assinatura de produção Android não foi configurada. Não use esses APKs como build de produção assinado.