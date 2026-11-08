# AutoRIP em PC servidor Linux com interface gráfica

Este perfil usa Ubuntu Desktop LTS em um PC dedicado, com o AutoRIP rodando como serviço `systemd` e Samba disponibilizando a entrada e os PRTs na rede local. O PrintExp permanece no computador conectado à impressora.

## Layout

O instalador cria:

```text
/srv/autorip/hot       entrada das artes
/srv/autorip/saida     PRTs prontos para o PrintExp
/srv/autorip/feito     originais processados
/srv/autorip/erro      entradas com falha
/srv/autorip/impressos controle local
/srv/autorip/recovery  recuperação de arquivamentos
/var/lib/autorip       configuração, journals, outbox e estado privado
/opt/autorip           código e ambiente Python
```

O serviço processa somente os caminhos locais em `/srv/autorip`. Os computadores da rede acessam esses diretórios por SMB; o RIP não depende de um volume de rede montado localmente.

## Instalação

### Criar a ISO automática

Se quiser criar uma mídia única que apague o SSD escolhido e instale tudo automaticamente, use um PC Linux x86_64 ou qualquer máquina capaz de manipular a ISO Ubuntu amd64:

```bash
sudo apt update
sudo apt install -y xorriso openssl
./deploy/linux-server/build_autorip_iso.sh \
  ubuntu-24.04-desktop-amd64.iso \
  autorip-server.iso
```

O gerador solicita hostname, usuário/senha administrativo, senha Samba e CIDR da rede local. A ISO instala Ubuntu Desktop, AutoRIP, Samba, XRDP, Cockpit e o serviço automático. Ela usa o layout automático do Ubuntu e pode apagar o maior disco selecionado pelo instalador; desconecte outros discos antes de inicializar a mídia, deixando conectado somente o SSD de destino e o dispositivo usado para boot.

As senhas são embutidas na ISO criada. Trate o arquivo como confidencial e apague-o depois da instalação. O ICC não é embutido: copie-o para `/var/lib/autorip/perfil.icc` após o primeiro boot.

1. Instale Ubuntu Desktop LTS no PC dedicado, com o PC ligado por Ethernet. A interface gráfica é útil para manutenção local; o worker do AutoRIP será iniciado como serviço, sem abrir uma segunda instância pela GUI.
2. Atualize o sistema e instale Git:

```bash
sudo apt update
sudo apt full-upgrade
sudo apt install -y git
```

3. Copie o projeto para o PC, entre na raiz e execute:

```bash
sudo ./deploy/linux-server/install_autorip_server.sh
```

O instalador solicita uma senha para o login compartilhado `autorip`. Essa é a senha usada no Windows para abrir os compartilhamentos.

O worker começa automaticamente no boot. O Ubuntu Desktop fornece a interface para manutenção, terminal, navegador e diagnóstico; não execute uma segunda cópia de `python -m autorip --gui` enquanto o serviço estiver ativo, pois ela iniciaria outro worker. O estado operacional deve ser acompanhado por `systemctl` e `journalctl`.

O instalador também instala **XRDP** e **Cockpit**. No Windows, abra `mstsc.exe` e conecte-se ao IP do servidor para acessar a área de trabalho. Para administração rápida, use `https://IP-DO-SERVIDOR:9090` no navegador. As regras do firewall são criadas para `AUTORIP_LAN_CIDR` (padrão `192.168.0.0/16`); para outra rede, instale com:

```bash
sudo AUTORIP_LAN_CIDR=192.168.1.0/24 \
  AUTORIP_DESKTOP_USER=nome-do-usuario \
  ./deploy/linux-server/install_autorip_server.sh
```

Não encaminhe as portas 3389 ou 9090 no roteador. Para acesso fora da rede, use VPN.

## Perfil ICC

Copie o perfil autorizado para um caminho privado, por exemplo:

```bash
sudo install -o autorip -g autorip -m 0640 /caminho/perfil.icc /var/lib/autorip/perfil.icc
sudoedit /var/lib/autorip/autorip.json
```

Altere:

```json
"icc_path": "/var/lib/autorip/perfil.icc"
```

Depois reinicie:

```bash
sudo systemctl restart autorip
sudo systemctl status autorip
```

O perfil não deve ser colocado no Git, no pacote de instalação ou em um compartilhamento público.

## IP fixo

O IP deve ser configurado no NetworkManager do Ubuntu. A forma mais segura é criar uma reserva DHCP no roteador pelo MAC address do servidor. Se o IP realmente precisar ser configurado no computador:

```bash
nmcli connection show
sudo nmcli connection modify "NOME-DA-CONEXAO" \
  ipv4.method manual \
  ipv4.addresses 192.168.1.50/24 \
  ipv4.gateway 192.168.1.1 \
  ipv4.dns "192.168.1.1 1.1.1.1"
sudo nmcli connection up "NOME-DA-CONEXAO"
```

Substitua interface, endereço, gateway e DNS pelos valores reais da rede. Faça essa alteração localmente no PC ou por acesso físico, pois uma configuração incorreta pode derrubar o acesso remoto.

## Acessar pelo Windows

No Explorador de Arquivos, use:

```text
\\192.168.1.50\AutoRIP-Entrada
\\192.168.1.50\AutoRIP-Saida
\\192.168.1.50\AutoRIP-Feito
\\192.168.1.50\AutoRIP-Erros
```

Informe o usuário `autorip` e a senha definida durante a instalação. Para mapear unidades:

```text
Z: → \\192.168.1.50\AutoRIP-Entrada
P: → \\192.168.1.50\AutoRIP-Saida
```

A entrada permite gravação. Saída, feito e erros ficam somente para leitura pela rede, reduzindo o risco de alguém apagar ou substituir um PRT durante o uso do PrintExp.

## Operação

- Copie a arte para `AutoRIP-Entrada`.
- Aguarde o PRT aparecer em `AutoRIP-Saida`.
- Abra o PRT no PrintExp do computador ligado à impressora.
- Não edite, renomeie ou mova arquivos enquanto o AutoRIP estiver processando.
- Não coloque o servidor e a impressora em redes Wi-Fi instáveis; o servidor deve usar Ethernet.

Comandos de diagnóstico:

```bash
sudo systemctl status autorip
sudo journalctl -u autorip -f
sudo systemctl restart autorip
sudo testparm -s
smbclient -L localhost -U autorip
```

## Backup

Faça backup periódico de:

```text
/var/lib/autorip/autorip.json
/var/lib/autorip/auth.json
/var/lib/autorip/outbox.json
/var/lib/autorip/perfil.icc
```

Os PRTs e as artes concluídas devem ter uma política própria de retenção. Não inclua senhas Samba ou tokens de integração em scripts e não compartilhe `auth.json`/`autorip.json` publicamente.

## Atualização

O serviço Linux usa atualização manual e `auto_update` fica desligado. Para atualizar:

1. Pare o serviço.
2. Faça backup da configuração e da outbox.
3. Substitua o código pela versão validada.
4. Execute novamente o instalador.
5. Confirme o ICC e os caminhos.
6. Inicie o serviço e acompanhe o journal.

```bash
sudo systemctl stop autorip
sudo cp -a /var/lib/autorip /var/backups/autorip-$(date +%F-%H%M%S)
sudo ./deploy/linux-server/install_autorip_server.sh
sudo journalctl -u autorip -n 100 --no-pager
```

## Limitações

A geração do PRT ainda precisa ser validada no PrintExp, na impressora, com a tinta, o filme e o perfil ICC reais. O servidor Linux não substitui o PrintExp nem o driver da impressora.
