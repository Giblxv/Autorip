# Estabilidade em lote: menos espera, mesmos PRTs

Continuação: [controles e capacidade para lotes longos](JOB-QUEUE.md).
Os tempos abaixo permanecem como registro desta medição do fluxo em lote.

Base: `104725c`, posterior às [duas campanhas do motor](RIP-WIDE-CAMPAIGN.md).
Esta etapa mede o fluxo de arquivos em lote separadamente das 41 rodadas
anteriores. Não altera `engine.py`, `prt.py` ou `morph.py`, nem acrescenta novas
rodadas à contagem histórica.

## Problema e mudança

O painel aguardava 0,5 segundo **por arquivo** antes de admiti-lo na fila.
A CLI aguardava 1 segundo por entrada na hot-folder e mais 0,25 segundo por
arquivo em processamento. Essas esperas se acumulavam mesmo quando todos os
arquivos já estavam completos.

Agora `_stable_files` captura a assinatura dos candidatos, compartilha a mesma
janela de espera entre eles e revalida cada arquivo ao consumir o iterador.
O painel usa essa verificação nos grupos de recuperação, hot-folder e uploads
manuais. A CLI compartilha as janelas de 1 e 0,25 segundo entre os respectivos
lotes. O número de RIPs simultâneos e o orçamento das tiras permanecem iguais.

Cada assinatura reúne dispositivo, inode, tamanho, mtime e ctime em nanossegundos.
`_signature` usa uma única consulta `stat(..., follow_symlinks=False)` e verifica
o modo retornado, eliminando as outras consultas de `islink`/`isfile`.
Não segue links simbólicos, aceita somente arquivos regulares e ignora entradas
vazias, ausentes ou inacessíveis. A observação armazena caminhos e metadados;
não carrega os pixels das imagens.

Um arquivo que muda durante a espera ou durante o processamento dos anteriores
fica para uma passagem seguinte. A segunda assinatura é consultada imediatamente
antes de liberar cada item, em vez de aprovar todo o lote antecipadamente.
A recuperação continua consultando a fila viva para proteger trabalhos ativos
e pausados, inclusive com aliases e diferenças de maiúsculas/minúsculas no Windows.
Journal, hash do PRT, fsync, publicação exclusiva e metadados auxiliares são mantidos.

## Medições

Linux, Python 3.12.14, quota de quatro CPUs. Sete repetições pareadas com ordem
alternada e aquecimento; tempos incluem as esperas reais. A entrada da fila é
medida com o observador de produção em uma passagem e o worker parado, separada
do RIP. A CLI mede `run_once` completo: espera, claim, RIP 720 × 2400 dpi, gravação,
sincronização, journal, metadados e arquivamento. Renderizador e demais módulos
compartilhados são os mesmos nos dois lados.

| Cenário | Base | Refinado | Resultado |
| --- | ---: | ---: | --- |
| Painel: admissão de 1 arquivo | 0,502 s | 0,502 s | Sem ganho confirmado |
| Painel: admissão de 16 arquivos | 8,011 s | 0,503 s | **15,91×** |
| CLI: RIP completo de 1 arte | 1,477 s | 1,464 s | Sem ganho confirmado |
| CLI: RIP completo de 8 artes | 11,718 s | 2,981 s | **3,93×** |

Intervalos bootstrap pareados de 95%: **15,895–15,925×** para a admissão de
16 arquivos e **3,883–3,987×** para o RIP completo do lote de oito. Os intervalos
dos casos com um único arquivo incluem 1; não se atribui ganho a esses casos.

O lote usa cópias da mesma arte RGBA de 256 × 192 pixels, com transparência,
branco e saída de 614 × 1536 pontos. Rótulos e margens ficam desligados nos dois
lados, sem perfil ICC externo. Em cada execução da CLI, os SHA-256 dos PRTs e os metadados são comparados,
e todos os arquivos precisam estar arquivados sem duplicação ou erro.

**15,91× se refere apenas à admissão na fila**, não ao renderizador nem ao
tempo total do painel. Os ganhos caem quando renderização, disco ou comunicação
com a impressora dominam o trabalho. Esta medição não inclui impressora física,
espera até o próximo polling, notificações ou geração das miniaturas do painel.

## Verificação e reprodução

- Testes determinísticos de janela compartilhada, arquivos alterados/removidos,
  lote vazio e substituição com tamanho e mtime preservados.
- Revalidação tardia: um item alterado enquanto o anterior é consumido não é liberado.
- Integração CLI: arte que muda durante o primeiro RIP permanece em processamento
  e é concluída na passagem seguinte, sem PRT incompleto ou encaminhamento indevido
  para erros.
- Integração do painel: lote completo sem RIP duplicado ou perda de metadados.
- Regressões existentes de recuperação, pausa/cancelamento, aliases e publicação.

Validação local: **280 testes aprovados em 43,44 s**, além do smoke v0.8.14 com
login, upload, geração do PRT 720 × 2400 dpi e encerramento.

Dados integrais e hashes (artefato histórico não versionado)
e [benchmark reproduzível](../../benchmarks/benchmark_batch_flow.py):

```bash
python benchmarks/benchmark_batch_flow.py --baseline-ref 104725c --repeat 7 --output /tmp/batch.json
python -m pytest -q
```

Nenhuma dependência nova ou mudança de DPI, canais, ICC ou modelo físico do branco.
O refinamento continua no PR #51.
