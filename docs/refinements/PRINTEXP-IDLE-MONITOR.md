# Menos trabalho no monitoramento ocioso do PrintExp

Base: `0eee88f`, release 0.8.30. Entrega: AutoRIP 0.8.31 / PrintExpAgent 0.2.1.

O agente repetia a espera de estabilidade e a leitura completa para SHA de cada
PRT, mesmo quando já aguardava autorização e permanecia inalterado. Em uma pasta
de saída compartilhada, isso também podia disputar recursos com o computador do RIP.

## Alterações

O agendamento contínuo em modo seguro/simulação usa a identidade, tamanho e datas
do arquivo para acompanhar a estabilidade e reconhecer os já registrados. Uma
observação conservadora entre varreduras mantém a janela mínima de estabilidade
mesmo se a varredura for lenta. Entradas removidas são descartadas do cache;
metadados alterados reiniciam a observação. Arquivos vazios permanecem pendentes.

O cache é somente de agendamento em modos sem impressão, fica em memória e é
descartado em cada início. Ao iniciar impressão automática ou executar `--once`,
a estabilidade e o SHA são verificados novamente antes dos comandos PrintExp.
Uma assinatura pré-calculada é rejeitada no caminho de impressão real.

Antes e depois do hash, os metadados são conferidos. Alterações durante a leitura
adiam o arquivo. A parada é observada durante a espera e entre blocos de 1 MiB
do hash. Não há cancelamento de impressão física já solicitada.

## Medição

Linux/Python 3.12, 128 arquivos sintéticos de 64 KiB, cadastro inicial fora do
cronômetro, oito varreduras por amostra, nove pares em ordem alternada:

| Métrica | Base | Candidato |
| --- | ---: | ---: |
| Mediana por oito varreduras | 71,43 ms | 5,82 ms |
| SHA recalculados nas amostras | 9.216 | 0 |
| Bytes lidos para SHA nas amostras | 576 MiB | 0 |

Redução observada de tempo: 91,86%. Foram comparados nome, SHA, estado e contador
de tentativas no SQLite, sem diferença. A base teve a espera de estabilidade
substituída por `True`, favorecendo a base e isolando o custo das releituras.

Os arquivos estavam sujeitos ao cache do sistema operacional. Não se trata de
medição de bytes físicos no NVMe, tráfego SMB, tempo de RIP ou produção da impressora.
O custo da primeira leitura continua existindo e não foi incluído nessas amostras.

## Reprodução e verificação

```bash
python benchmarks/benchmark_agent_idle.py --baseline-ref 0eee88f --output /tmp/agent-idle.json
python -m pytest -q tests/test_print_agent_idle.py tests/test_print_agent_service.py tests/test_print_agent.py tests/test_printexp_network.py
python -m pytest -q
```

Regressões cobrem registro em lote, invalidação/remoção do cache, novo início com
impressão, hash completo antes dos comandos, parada durante hash, alteração durante
leitura, compartilhamento temporariamente bloqueado e arquivo removido na varredura.
O smoke da janela usa o modo seguro e conexão simulada. O workflow Windows mantém
a verificação da interface dentro do EXE compilado. Não houve impressão física.
