# Guia rápido: apps móveis e conexão ao AutoRIP

O celular é um controle remoto do painel; o RIP continua sendo executado no computador. Deixe o AutoRIP rodando no Windows ou Linux e mantenha computador e telefone na mesma rede Wi-Fi/LAN. Não use a rede Wi-Fi de convidados, que costuma bloquear dispositivos entre si.

## 1. Instalar o app Android

Baixe a [prévia AutoRIP Mobile 0.2.1](https://github.com/Giblxv/Autorip/releases/tag/mobile-v0.2.1) e escolha `AutoRIP-Mobile-debug.apk` para o app padrão ou `AutoRIP-Mobile-optimized.apk` para a variante R8 de teste. Abra o APK no Android e confirme a instalação. Se o Android pedir autorização para instalar apps dessa fonte, permita apenas para o navegador/gerenciador usado na instalação; depois, você pode desativar essa permissão nas configurações do telefone.

São APKs de prévia assinados com chave debug, não publicados na Play Store. A variante Optimized tem identificador de pacote separado e instala como app diferente; é apenas para comparação, não substitui o app padrão. O APK padrão de uma execução futura pode ter outra chave debug: se o Android rejeitar a atualização, desinstale a prévia antiga antes de instalar a nova. Isso apaga apenas endereços recentes locais, não os arquivos do computador.

O instalador Windows também mostra um QR para esse APK. Depois da instalação, os mesmos códigos ficam disponíveis em **Ajuda** no painel do AutoRIP.

## 2. Instalar o app iPhone/iPad

O projeto Flutter para iOS está em [`mobile_ios/`](../mobile_ios/), mas ainda não existe um IPA assinado, App Store ou convite TestFlight para baixar. Para testar agora, é necessário um Mac com Xcode: abra `mobile_ios/ios/Runner.xcworkspace` no Xcode, selecione a equipe de assinatura Apple em **Signing & Capabilities**, conecte o iPhone e execute o app pelo Xcode. Antes, rode `flutter pub get` na pasta `mobile_ios`. O projeto está configurado para iOS 15 ou posterior.

Para distribuir sem usar o Xcode em cada telefone, será preciso configurar assinatura e distribuição Apple, por exemplo App Store Connect/TestFlight. Isso requer uma equipe/conta Apple Developer e ainda não está configurado neste repositório. Não baixe ou instale IPA de sites de terceiros.

## 3. Descobrir o IP do computador

No painel do computador, clique em **Conectar celular** e entre ou crie sua senha. A lista mostra automaticamente os IPv4 privados e os adaptadores do computador. Escolha o Wi-Fi ou Ethernet conectado à mesma rede do telefone. Clique em **Atualizar IPs** se a rede mudar.

Para conferir manualmente, use `ipconfig` no Windows ou `hostname -I` no Linux. O endereço normalmente começa com `192.168.`, `10.` ou `172.16` a `172.31`. Exemplo usado abaixo: `192.168.1.50`.

Se esse IP mudar a cada reinicialização, reserve-o no roteador (reserva DHCP) ou repita a configuração com o endereço novo.

## 4. Iniciar o AutoRIP aceitando o telefone

O servidor aceita apenas o próprio computador por padrão. Abra o programa normalmente e, na janela nativa, use **Abrir painel e configurações**. No painel, escolha **Conectar celular**, selecione seu IPv4 e clique em **Ativar acesso e gerar QR**. Isso abre somente a interface escolhida, na mesma porta do painel, sem reiniciar a fila. O acesso e o IPv4 escolhido ficam salvos para a próxima abertura. Para desligar, use **Desativar acesso** nesse mesmo diálogo.

Se o Firewall do Windows perguntar, permita o AutoRIP para **redes privadas**. O programa não altera regras do firewall automaticamente. Se trocar de rede e o IP salvo deixar de pertencer ao computador, volte ao diálogo e selecione o novo IPv4.

### Alternativa manual e versões anteriores

Em versões sem o botão de ativação, configure o **IP IPv4 real do computador** no `AUTORIP_BIND_HOST` ao iniciar o modo web. Isso limita a escuta à interface escolhida. Não use `0.0.0.0` neste tutorial. Um listener iniciado por variável de ambiente precisa ser desativado na configuração de inicialização; o botão do painel só desliga o listener adicional criado pelo próprio painel.

### Windows

Abra o PowerShell na pasta onde está `AutoRIP.exe`. Troque o IP do exemplo pelo que encontrou com `ipconfig` e rode:

```powershell
$env:AUTORIP_BIND_HOST = "192.168.1.50"
$env:AUTORIP_PUBLIC_HOST = "192.168.1.50"
$env:AUTORIP_NOBROWSER = "1"
& ".\AutoRIP.exe" --web
```

Se o executável estiver em outra pasta, use o caminho completo entre aspas, por exemplo `& "C:\caminho\AutoRIP.exe" --web`. Deixe essa janela aberta enquanto usa o telefone. O comando `--web` abre o painel no navegador; no modo normal, use **Abrir painel e configurações** na janela do programa.

Se o Firewall do Windows perguntar, permita o AutoRIP somente em **redes privadas**, nunca em redes públicas. Se não houver aviso, crie uma regra de entrada TCP para a porta que o AutoRIP imprimiu no terminal, limitada ao perfil **Privado** e, se possível, ao escopo **Sub-rede local**.

### Linux

Abra um terminal na pasta do repositório AutoRIP. Se ainda não instalou as dependências Python, faça isso uma vez:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Em cada início, use o IP encontrado no passo anterior:

```bash
source .venv/bin/activate
export AUTORIP_BIND_HOST=192.168.1.50
export AUTORIP_PUBLIC_HOST=192.168.1.50
export AUTORIP_NOBROWSER=1
python -m autorip --web
```

Deixe o terminal aberto. Se o Linux usa UFW, permita a porta somente a partir da sub-rede local. Ajuste o exemplo `192.168.1.0/24` à sua rede e `8765` à porta mostrada pelo AutoRIP:

```bash
sudo ufw allow from 192.168.1.0/24 to any port 8765 proto tcp
```

O servidor tenta a porta `8765` e, se ela estiver ocupada, tenta as seguintes. Use no app exatamente a URL que aparece na mensagem `AutoRIP em ...` no terminal. Ao terminar, feche o programa com `Ctrl+C`; no Windows, feche a janela do terminal.

Quando `AUTORIP_BIND_HOST` contém o IP específico do servidor, o AutoRIP já permite esse host no painel. Por isso, não é necessário configurar `AUTORIP_ALLOWED_HOSTS` para o uso simples por IP. Se você optar por `0.0.0.0` ou por outro nome de host, precisará configurar a lista permitida separadamente.

## 5. Conectar o telefone

1. Conecte o telefone à mesma rede privada do computador.
2. No computador, escolha **Conectar celular**, selecione o IPv4 da rede e use **Ativar acesso e gerar QR**. O QR gerado contém apenas endereço e porta, não a senha. Se usar a configuração manual, abra o painel pelo endereço `http://IP:porta` impresso pelo servidor.
3. Na prévia móvel 0.2.1, use **Escanear QR** para ler o código de conexão; se a câmera estiver indisponível, digite `http://IP:porta`. Versões antigas também podem usar o endereço manualmente. Os QR de **Ajuda** abrem a página de download/instruções e não fazem o pareamento.
4. No primeiro acesso, crie a senha do painel; depois, entre com essa senha. O app guarda até cinco endereços recentes, mas não guarda a senha.

O instalador e **Ajuda** mostram dois QR de distribuição: Android abre a página da prévia móvel 0.2.1, com APK padrão e variante Optimized; iPhone/iPad abre este guia, pois ainda não há IPA assinado publicado.

No app iOS, HTTP só é aceito para endereços locais/privados. Para acesso externo, use HTTPS e VPN/rede privada; não encaminhe a porta do AutoRIP no roteador para a internet.

## Se não conectar

Confirme primeiro que o AutoRIP continua em execução, que telefone e computador estão na mesma rede e que o endereço e a porta digitados são os exibidos no QR. Se o IP mudou, use **Atualizar IPs**, escolha o novo endereço e ative novamente. Na configuração por variáveis de ambiente, reinicie o programa após alterar as variáveis. Se aparecer **403**, confira se o IP digitado é o que foi ativado. Se houver timeout, confira o firewall e o isolamento de clientes Wi-Fi/rede de convidados. Um pedido de senha é esperado e confirma que o painel respondeu.
