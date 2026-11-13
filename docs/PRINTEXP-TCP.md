# Verificação da integração TCP com PrintExp

O [plano de integração](PRINTEXP-INTEGRACAO-PLANO.md), de 13/11/2026, detalha o
agente Windows, a ponte de arquivos, o adaptador TCP nativo, os estados e os
critérios de validação. O [estudo comparativo dos RIPs](research/RIP-COMPARATIVO.md)
registra as referências e os achados reproduzidos no agente atual.

O AutoRIP atual gera arquivos PRT e mantém uma fila de arquivos. Ele ainda não
implementa um cliente TCP de recepção do PrintExp nem o protocolo da controladora.
O usuário informou que sua instalação do PrintExp aceita TCP. As imagens
fornecidas em 13/11/2026 mostram a versão `5.7.6.5.122.R.BS`, TCP selecionado,
IP local `192.168.0.215` e destino exibido `192.168.127.10:5001`. A imagem
seguinte mostra o FlexiPRINT MiniTX F-PRINT Edition com `TCP/IP` e destino
`192.168.127.11:9100` na janela Mudar porta. Esse é o endereço candidato para
receber os trabalhos; ainda faltam confirmar a aplicação da configuração,
o resultado do teste/envio e o processo receptor.

Os campos Server IP/port aparecem acinzentados e os valores coincidem com a
comunicação da placa na distribuição de referência abaixo. Portanto, o envio
AutoRIP → PrintExp não deve assumir esse destino. O [plano atualizado](PRINTEXP-INTEGRACAO-PLANO.md#instalação-mostrada-nas-imagens-do-usuário)
registra a observação e o que ainda depende de verificação no computador.

## Evidência encontrada

O [guia da Ricoma](https://support.ricoma.com/hc/en-us/articles/40213625226771-DTF-Aire-PrintExp-Hosonsoft-Software-Installation)
orienta selecionar LINK TCP durante a instalação. Isso confirma uma modalidade
de comunicação, mas não documenta o formato dos pacotes de um cliente RIP.

Uma [distribuição pública PrintExp 5.7.6.5.103, de 2022](https://cncu.co.za/Other-Softwares/AM.CO.ZA%20PrintEXP%20Printer%20Control%20%26%20Alignment%20Software/PrintExp_X64_V5.7.6.5.103.BS_20220530/)
lista `NWReceive.exe`, `NWReceiveProc.dll` e `TcpIp.dll`. Seu
[Project.ini](https://cncu.co.za/Other-Softwares/AM.CO.ZA%20PrintEXP%20Printer%20Control%20%26%20Alignment%20Software/PrintExp_X64_V5.7.6.5.103.BS_20220530/Project.ini)
separa três configurações:

| Seção | Valores dessa distribuição | Comentário no arquivo |
| --- | --- | --- |
| `COMM_CONFIG` | `ServerIP=192.168.127.10`, `ServerPort=5001` | Endereço/porta TCP da placa |
| `TCP_IP` | `ADDR=127.0.0.1`, `PORT=9100` | RIP e impressão simultâneos |
| `PLATFORM_CONFIG` | `ENABLE=0`, `TCP_SERVER_PORT=5678`, `TCP_DATA_PORT=5679` | Interface de plataforma desabilitada, com portas separadas para comandos e dados PRN |

São valores de referência de outra distribuição, não as configurações do usuário.
Não justificam escolher automaticamente 9100, 5001 ou 5679 para enviar um PRT.
O endereço de loopback também não prova que o receptor esteja exposto à LAN.

## Dados necessários e validação

- IP do computador que executa o receptor PrintExp/NWReceive, identificado
  separadamente do IP da placa da impressora; confirmar o papel de
  `192.168.127.11` e a interface local mostrada como `192.168.0.215`.
- Confirmar que a configuração FlexiPrint `TCP/IP → 192.168.127.11:9100`
  foi aplicada e funciona; a versão PrintExp e os valores exibidos já estão
  registrados no plano.
- Protocolo documentado/SDK ou exemplo autorizado da troca entre FlexiPrint e
  PrintExp: abertura do trabalho, tamanho/nome, dados, confirmações e encerramento.
- Um PRT de teste já aceito pela mesma versão do PrintExp, para separar problemas
  de transporte de problemas do formato raster.

Primeiro deve ser verificada a conexão, sem enviar trabalho. No Windows da mesma
rede, o comando é `Test-NetConnection -ComputerName IP -Port PORTA`, usando os
valores reais. Uma conexão TCP estabelecida não confirma aceitação do PRT ou
impressão concluída. A confirmação depende da resposta do protocolo/aplicativo.

O teste de compatibilidade deve rodar no computador do usuário ou por acesso de
rede autorizado; o ambiente de desenvolvimento em nuvem não alcança sua LAN
automaticamente. Não foi feita conexão à impressora ou enviado arquivo nesta
verificação.

Para localizar a porta no Windows, abra o PrintExp/NWReceive no modo de recepção
e consulte os listeners desses processos no PowerShell:

```powershell
$printExpIds = @(Get-Process -Name 'PrintExp*', 'NWReceive*' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
Get-NetTCPConnection -State Listen | Where-Object { $_.OwningProcess -in $printExpIds } | Select-Object OwningProcess, LocalAddress, LocalPort
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' } | Select-Object InterfaceAlias, IPAddress
```

Para distinguir uma conexão de saída para a placa de uma porta de recepção,
consulte também as conexões estabelecidas dos mesmos processos:

```powershell
Get-NetTCPConnection -State Established | Where-Object { $_.OwningProcess -in $printExpIds } | Select-Object OwningProcess, LocalAddress, LocalPort, RemoteAddress, RemotePort
```

Uma conexão desses processos para `192.168.127.10:5001` ajudaria a confirmar
o papel desse destino. O listener que recebe os trabalhos pode pertencer a
outro executável: se não houver resultado, confira o nome do receptor instalado.
Essas consultas apenas leem o estado do Windows; não enviam arquivos nem mudam
IP, porta, firmware ou parâmetros da impressora.

Para identificar especificamente o dono da porta candidata, execute no
computador que possui o endereço `192.168.127.11`:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 9100 | ForEach-Object {
    $connection = $_
    [pscustomobject]@{
        LocalAddress = $connection.LocalAddress
        LocalPort = $connection.LocalPort
        ProcessId = $connection.OwningProcess
        ProcessName = (Get-Process -Id $connection.OwningProcess).ProcessName
    }
}
```

O comando consulta a máquina em que é executado; não interroga outro computador
da rede. Se o destino for outro equipamento, essa consulta local não resolve a
identidade remota. Registrar também o resultado de Testar no FlexiPrint.

Use o IP da interface conectada à mesma rede do computador que enviará os
arquivos. `0.0.0.0` e `::` são endereços de escuta, não o IP a configurar no
cliente; `127.0.0.1` e `::1` restringem aquela escuta ao próprio computador. Se não
aparecer um listener, confirme o modo de recepção e o nome real do processo.
Essas consultas não enviam dados nem identificam o protocolo dos trabalhos.

Após identificar o protocolo, o cliente poderá transmitir em blocos, limitar
tempo de conexão/envio e registrar confirmações. Reenvio automático de uma
transferência incerta precisa considerar duplicação de trabalhos. Até essa
validação, não há envio TCP habilitado no AutoRIP.
