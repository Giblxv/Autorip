# AutoRIP Mobile

Cliente Android baseado em Capacitor para abrir o painel web do AutoRIP em um servidor interno. O APK não embute o motor RIP: o processamento continua no computador/servidor que executa o AutoRIP.

## Servidor interno

Por segurança, o servidor continua escutando em `127.0.0.1` por padrão. Para permitir o telefone na LAN, configure explicitamente no computador do AutoRIP:

```bash
AUTORIP_BIND_HOST=0.0.0.0 \
AUTORIP_ALLOWED_HOSTS=192.168.1.50,localhost,127.0.0.1 \
AUTORIP_PUBLIC_HOST=192.168.1.50 \
python autorip_gui.py --web
```

Substitua `192.168.1.50` pelo endereço real do servidor e libere somente a porta escolhida no firewall da rede privada. A senha do painel continua obrigatória. Para uso fora da rede local, prefira HTTPS e uma VPN/rede privada; não exponha a porta HTTP diretamente à internet.

## Build local

```bash
npm install
npx cap sync android
cd android
./gradlew assembleDebug
```

O artefato de teste fica em `android/app/build/outputs/apk/debug/app-debug.apk`. O app aceita conexão manual ou leitura do QR de endereço exibido no painel AutoRIP. Ao abrir pela primeira vez, informe o endereço do servidor; o app guarda até cinco endereços recentes localmente e não contém credenciais.

Para testar a variante não depurável com R8 e remoção de recursos não usados, execute `npm run android:optimized`. O APK fica em `android/app/build/outputs/apk/optimized/app-optimized.apk`; instala como `com.giblxv.autorip.optimized` para coexistir com o app normal e usa a chave debug, portanto serve para avaliação, não para publicação de produção. O workflow compara tamanhos de debug, optimized e release e disponibiliza os APKs debug e optimized como artefatos.

A variante `release` também ativa R8 e resource shrinking, mas `assembleRelease` gera APK não assinado enquanto não houver uma chave de produção configurada. O APK atualmente anexado à release móvel permanece o debug existente até que uma assinatura estável de produção seja configurada e validada.

## Release

O workflow `mobile-apk.yml` gera o APK em um runner Ubuntu quando acionado manualmente ou quando uma tag `mobile-v*` é criada. A publicação usa uma release móvel separada, evitando misturar o APK com a release Windows sem validação.
