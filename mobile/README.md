# AutoRIP Mobile

Cliente Android baseado em Capacitor para abrir o painel web do AutoRIP em um servidor interno. O APK não embute o motor RIP: o processamento continua no computador/servidor que executa o AutoRIP.

## Servidor interno

O servidor escuta em `127.0.0.1` por padrão. No painel do computador, entre/crie sua senha, escolha **Conectar celular**, selecione o IPv4 da rede do telefone e use **Ativar acesso e gerar QR**. A configuração fica salva, e o listener da interface escolhida pode ser desligado no mesmo diálogo, sem reiniciar a fila. A senha continua obrigatória no telefone. Veja o [guia de conexão](../docs/GUIA-APPS-MOVEIS.md).

Como alternativa para versões anteriores, configure a interface explicitamente ao iniciar:

```bash
AUTORIP_BIND_HOST=192.168.1.50 \
AUTORIP_ALLOWED_HOSTS=192.168.1.50,localhost,127.0.0.1 \
AUTORIP_PUBLIC_HOST=192.168.1.50 \
python autorip_gui.py --web
```

Substitua `192.168.1.50` pelo endereço real do servidor e libere somente a porta escolhida no firewall da rede privada. A senha do painel continua obrigatória. Para uso fora da rede local, prefira HTTPS e uma VPN/rede privada; não exponha a porta HTTP diretamente à internet.

## Build local

```bash
npm ci
npm run android:debug
```

O artefato de teste fica em `android/app/build/outputs/apk/debug/app-debug.apk`. O app aceita conexão manual ou leitura do QR de endereço exibido no painel AutoRIP. Ao abrir pela primeira vez, informe o endereço do servidor; o app guarda até cinco endereços recentes localmente e não contém credenciais.

`npm run build` gera módulos em `public/bundle/`. O leitor de QR e o runtime Capacitor são carregados apenas ao tocar em **Escanear QR**; a abertura para conexão manual não precisa desses módulos. Os comandos `cap:sync` e `android:*` recompilam o JavaScript antes de sincronizar o Android. Não edite os módulos gerados manualmente.

Para testar a variante não depurável com R8 e remoção de recursos não usados, execute `npm run android:optimized`. O APK fica em `android/app/build/outputs/apk/optimized/app-optimized.apk`; instala como `com.giblxv.autorip.optimized` para coexistir com o app normal e usa a chave debug, portanto serve para avaliação, não para publicação de produção. O workflow compara tamanhos de debug, optimized e release e disponibiliza os APKs debug e optimized como artefatos.

A variante `release` também ativa R8 e resource shrinking, mas `assembleRelease` gera APK não assinado enquanto não houver uma chave de produção configurada. A prévia `mobile-v0.2.1` publica APKs Debug e Optimized, ambos assinados com a chave debug do runner, além de checksums. A chave debug não é uma assinatura estável de produção; se o Android recusar uma atualização, desinstale a prévia anterior. O APK Optimized usa o pacote separado `com.giblxv.autorip.optimized`.

## Release

O workflow `mobile-apk.yml` compila Android em Ubuntu e iOS em macOS, em PRs
relevantes, acionamento manual ou tags `mobile-v*`. A prévia `mobile-v0.2.1`
inclui APK padrão, Optimized, release sem assinatura, o aplicativo iOS sem
assinatura e `SHA256SUMS.txt`. Android e iOS precisam compilar antes da
publicação. Use o [guia rápido](../docs/GUIA-APPS-MOVEIS.md) para instalação e
conexão. A publicação móvel fica separada da release Windows.
