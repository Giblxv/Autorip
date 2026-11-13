# Descoberta IPv4 do computador PrintExp

O AutoRIP pode listar seus IPv4 locais, descobrir agentes AutoRIP na mesma rede e verificar a conexão TCP do destino. Em **Configurações → Conexão PrintExp**, o endereço do computador receptor e a porta ficam salvos junto das outras configurações. A porta inicial é `9100`.

## Usar em dois computadores

1. No computador que executa o PrintExp, instale a versão atualizada do agente. Para anunciar apenas a rede, sem monitorar pastas ou imprimir, execute:

   ```powershell
   .\PrintExpAgent.exe --network-discovery --print-port 9100
   ```

   Na execução normal do agente, o anúncio também fica ativo por padrão. O campo `network_discovery: false` em `print-agent.json` desativa esse anúncio; `printexp_port` define a porta candidata anunciada. A impressão automática continua com seu controle próprio e padrão desabilitado.

2. No computador do AutoRIP, abra **Configurações → Conexão PrintExp → Buscar PrintExp na rede**.
3. Se houver um único endereço, ele preenche o formulário e a conexão TCP é verificada. Havendo vários computadores ou interfaces, escolha o endereço correspondente ao computador PrintExp.
4. Confira o resultado e clique em **Salvar**. A descoberta não persiste alterações sozinha. Um IP digitado enquanto uma busca está em andamento é preservado.

**Verificar conexão** funciona também com IP informado manualmente. A consulta abre e fecha uma conexão TCP, sem enviar comandos ou PRT. O resultado indica alcançabilidade naquele momento; a aceitação dos trabalhos e a compatibilidade do protocolo nativo PrintExp são verificações separadas.

O texto **IPv4 deste computador (AutoRIP)** identifica as interfaces do servidor AutoRIP. Em dois computadores, esse endereço não é automaticamente o destino da impressão. Os resultados de descoberta vêm do agente executado no computador receptor. Uma porta 9100 aberta em outro equipamento não é usada como identificação de PrintExp.

## Rede e limites

- A descoberta usa mDNS na LAN, UDP `5353`, com tipo de serviço `_autorip-pe._tcp.local.`. Não há varredura das portas de todos os computadores.
- São aceitos IPv4 privados `10.x`, `172.16–31.x` e `192.168.x`. Loopback, link-local e IPv6 ficam fora dessa configuração para duas máquinas.
- O anúncio é uma indicação do agente, sem autenticação de identidade. A seleção continua no formulário e o teste TCP não certifica o software remoto.
- Wi-Fi com isolamento de clientes, VLANs ou firewall podem impedir descoberta. Nesse caso, use o IPv4 do receptor obtido com `ipconfig`, a porta configurada e **Verificar conexão**. Confira as regras específicas da rede local.
- A partir da v0.8.27, o agente acompanha mudanças de IP/interface e recria o anúncio de rede automaticamente. A consulta é periódica, a cada cinco segundos, além do tempo de registro mDNS. Após uma mudança, repita a busca no painel e use **Salvar** para atualizar o destino persistido. Prefira reserva DHCP para manter esse destino estável.
- Se o agente iniciar antes de a rede obter IPv4 ou encontrar uma falha temporária de anúncio, ele permanece aguardando e tenta novamente. O modo dedicado não precisa carregar a configuração de produção para fazer essa recuperação.
- Anúncios removidos e endereços substituídos durante uma busca são descartados. A busca também atualiza a lista das interfaces locais; respostas antigas não substituem a consulta mais recente.
- A descoberta usa os endereços atuais de cada interface; não fixa os IPs das imagens de exemplo no código e não modifica configurações da controladora.

## Diagnóstico sem imprimir

Para gravar uma lista de IPv4 locais em um arquivo, sem carregar a configuração de produção e sem conectar à impressora:

```powershell
.\PrintExpAgent.exe --network-info "$env:TEMP\autorip-ipv4.json"
Get-Content "$env:TEMP\autorip-ipv4.json"
```

O modo de descoberta isolada permanece ativo até encerrar o processo. Ao executá-lo por Python em um terminal, `Ctrl+C` encerra o anúncio:

```powershell
python agent\print_agent.py --network-discovery
```

O JSON de diagnóstico inclui a versão do agente. A atualização de recuperação de rede acompanha o `PrintExpAgent` 0.1.1; atualize o executável também no computador receptor.

## Escopo desta entrega

Esta entrega implementa descoberta, seleção, teste de conexão e persistência do destino. O cliente nativo de envio de PRT ao PrintExp continua dependente da especificação/validação do protocolo. Os controles de rede não iniciam impressão, alteram firmware ou enviam arquivos.

As APIs de consulta, descoberta e teste exigem autenticação do painel. Uma única operação de descoberta/teste ocorre por vez; a descoberta limita resultados e tempo de resolução. Fechar o diálogo ou trocar de sessão invalida respostas antigas no painel.
