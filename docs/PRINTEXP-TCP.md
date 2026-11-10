# Verificação da integração TCP com PrintExp

O AutoRIP atual gera arquivos PRT e mantém uma fila de arquivos. Ele ainda não
implementa um cliente TCP de recepção do PrintExp nem o protocolo da controladora.
O usuário informou que sua instalação do PrintExp aceita TCP; IP, porta e versão
ainda precisam ser informados para validar a integração real.

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
  separadamente do IP da placa da impressora.
- Versão do PrintExp, porta e modalidade TCP configuradas no PrintExp/FlexiPrint.
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

Após identificar o protocolo, o cliente poderá transmitir em blocos, limitar
tempo de conexão/envio e registrar confirmações. Reenvio automático de uma
transferência incerta precisa considerar duplicação de trabalhos. Até essa
validação, não há envio TCP habilitado no AutoRIP.
