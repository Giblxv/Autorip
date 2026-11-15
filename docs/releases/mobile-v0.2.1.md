# AutoRIP Mobile 0.2.1 (prévia)

Atualiza o tema escuro Looney nos clientes Android/iOS e no painel aberto pelo
aplicativo, mantendo conexão HTTP(S), leitor QR e histórico local. O RIP é
executado no computador servidor AutoRIP.

## Pacotes

- `AutoRIP-Mobile-debug.apk`: Android padrão, assinado com chave de teste.
- `AutoRIP-Mobile-optimized.apk`: Android com R8 e remoção de recursos,
  assinado com chave de teste e pacote separado `com.giblxv.autorip.optimized`.
- `AutoRIP-Mobile-release-unsigned.apk`: compilação Android release sem
  assinatura de produção; precisa ser assinada antes de instalar/distribuir.
- `AutoRIP-iOS-unsigned.app.zip`: aplicativo iOS nativo compilado no macOS/Xcode,
  sem assinatura Apple. Não é um IPA instalável; precisa de assinatura e
  provisionamento para dispositivo/TestFlight/App Store.
- `COMO_USAR.txt`: instruções Android e conexão com o servidor.
- `SHA256SUMS.txt`: hashes de todos os pacotes binários desta prévia.

Os APKs de teste usam a chave debug do runner, que pode diferir da prévia
anterior. Se o Android recusar a atualização por assinatura diferente,
desinstale a prévia anterior e instale a nova; isso pode apagar o histórico
local de endereços. O servidor e suas artes não são apagados.

Android e iOS são compilados antes da publicação desta prévia. O código Flutter
também passa por análise estática e testes. Esta versão não representa uma
publicação nas lojas de aplicativos.

[Guia de instalação e conexão](../GUIA-APPS-MOVEIS.md).
