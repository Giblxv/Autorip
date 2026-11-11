# Desempenho do painel no computador e no celular

A página suspende os três timers de estado, impressões e hot folder quando fica oculta. Ao voltar, atualiza imediatamente e mantém um único conjunto de timers. Atualizações forçadas de ações continuam permitidas. Respostas anteriores ao retorno são invalidadas pelo controle de revisão existente. O servidor continua processando trabalhos normalmente.

A fila reutiliza os cartões de trabalhos cuja assinatura não mudou. O cache guarda somente os IDs presentes na resposta atual e é limpo ao bloquear ou encerrar. Reordenação, seleção, foco, controles de pausa/retomada/cancelamento e aviso de conclusão preservam o comportamento anterior. O conteúdo e o desenho dos cartões permanecem iguais.

## Provas de trabalho evitado

Comparação com `cab0b05` (RGB nativo e cache de ruído já integrados). Em Chromium 156, com eventos de visibilidade controlados:

- 30 acionamentos de estado e 10 de cada lista: **50 consultas antes, zero depois**, tanto em viewport desktop como 390 × 844;
- atualização de um progresso em 100 cartões: **200 nós removidos/adicionados antes, 2 depois**; 99 cartões preservados;
- página oculta: três timers antes, zero depois; retorno imediato aos três recursos;
- resposta pendente no retorno: descartada antes de renderizar dados antigos;
- ações forçadas em segundo plano, encerramento, remoção de cartões e troca de sessão passaram nas verificações.

A suíte final passou **36 cenários de navegador**. Os 23 cenários existentes também passam no HTML antigo; as falhas adicionais do relatório anterior são testemunhos das otimizações, não falhas de infraestrutura. A suíte Python passou **1088 testes** antes da alteração apenas da versão para 0.8.22. As verificações do instalador e a matriz da revisão final são registradas separadamente.

## Renderização controlada

Foram usados **44 processos novos do Chromium**, ordem pareada aleatória, 100 cartões sintéticos sem miniaturas, cinco atualizações de aquecimento e 50 medidas por processo. Mede `renderJobs` mais layout forçado, excluindo navegação, autenticação e inicialização. Movimento reduzido está habilitado. A subárvore HTML final da fila tem SHA-256 idêntico nos dois lados de todas as baterias.

| Bateria | Desktop antigo → novo | Viewport móvel antigo → novo |
| --- | --- | --- |
| Exploração, 3 pares | 25,60 → 1,10 ms | 17,35 → 1,05 ms |
| Confirmação, 5 pares | 30,60 → 1,10 ms | 18,80 → 1,10 ms |
| A/A, 3 pares | razão 0,963 | razão 1,071 |

Esses valores descrevem o cenário sintético e incluem a variação do ambiente. Não medem velocidade total do aplicativo, bateria, hardware Android/iOS ou FPS em um telefone. A redução de chamadas e de reconstrução de cartões é a evidência principal de trabalho evitado.

[Relatórios brutos, decisão e fontes](../../benchmarks/campaign_runs/2026-11-11-panel-performance/).

```sh
AUTORIP_PYTHON=.venv/bin/python node tools/smoke_polling_ui.cjs /tmp/panel-current
AUTORIP_PYTHON=.venv/bin/python AUTORIP_POLLING_BASELINE=cab0b05 node tools/smoke_polling_ui.cjs /tmp/panel-before
AUTORIP_PYTHON=.venv/bin/python node benchmarks/benchmark_panel_jobs.cjs --baseline-ref cab0b05 --repeat 5 --output /tmp/panel-benchmark.json
```

Requer Playwright e Chromium. O script aceita `AUTORIP_CHROMIUM` para usar um navegador instalado. O ZIP e o manifesto preservam os HTMLs e scripts medidos. O aplicativo nativo Android abre este painel no servidor; nenhuma nova dependência ou atualização de APK é necessária para receber a página atualizada.

A investigação do RIP foi pausada após sete hipóteses sem ganho sobre `cab0b05`, sem contar a rodada parcial 8. O contador reinicia após estas duas melhorias validadas. As sequências anteriores permanecem separadas.
