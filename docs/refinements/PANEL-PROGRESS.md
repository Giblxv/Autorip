# Atualizar o progresso sem recriar o cartão

Base: AutoRIP 0.8.42, commit `66dc2723512ba1f67c486defc479011c8aeefdd3`.
O painel já preservava os trabalhos sem mudanças, mas reconstruía o cartão
ativo a cada novo valor de progresso. Isso removia e recriava a barra,
botões e imagem de prévia, quando presente.

Agora a assinatura dos dados estruturais exclui somente `progress`.
Enquanto os demais campos permanecem iguais, o cartão atualiza seus
elementos de progresso. Se o percentual arredondado continua igual, não
escreve esses atributos novamente. Nome, status, erro, prévia e quaisquer
outros campos continuam provocando a atualização completa do cartão.

Arredondamento, limites de 0–100%, emoji, acessibilidade, seleção, foco,
rolagem, pausa, retomada, cancelamento e aviso de conclusão preservam suas
regras. A fase da animação e a imagem decodificada continuam no mesmo nó.
O cache segue limitado aos IDs da resposta atual e é limpo ao bloquear,
trocar de sessão ou encerrar. As referências novas são apenas elementos
já pertencentes a cada cartão, sem cache adicional de artes ou arquivos.

## Trabalho evitado

Na prova com 100 cartões e 50 atualizações do trabalho ativo:

| Cenário | v0.8.42 | Novo painel |
| --- | ---: | ---: |
| Cartões preservados | 99 | 100 |
| Elementos criados, sem miniaturas | 450 | 0 |
| Elementos criados, com miniaturas | 500 | 0 |
| Imagens criadas, com miniaturas | 50 | 0 |

As contagens vêm de chamadas a `document.createElement` durante as
atualizações. Não significam ausência de qualquer mutação DOM: atributos
da barra e o texto do emoji continuam mudando quando necessário.

Nas provas assíncronas desktop e móvel, cinco atualizações preservaram
cartão, imagem, URL, fase da animação, seleção e botão focado; não criaram
novos URLs de objeto nem removeram/adicionaram cartões. Quatro mudanças
entre 37,001% e 37,49% mantiveram o percentual visível em 37%, com zero
mutações observadas na fila. A base produziu oito mutações nesse cenário.

O backend atual normalmente associa a miniatura ao trabalho pronto.
Portanto, o cenário de progresso com imagem é sintético e não implica que
todo trabalho em processamento já tenha uma prévia. A melhoria de cartões
e controles também se aplica às respostas reais sem imagem.

## Renderização controlada

60 processos novos de Chromium: cinco pares por viewport/cenário e cinco
pares A/A por viewport, com ordem AB/BA equilibrada e embaralhada. Foram
3.000 atualizações cronometradas, mais 3.000 atualizações instrumentadas
fora do cronômetro, e cinco aquecimentos por processo. O fixture é montado
antes da medição, com fontes prontas e rede estabilizada. Não houve
concorrência com pytest. O cronômetro cobre
`renderJobs` e layout forçado de 100 cartões, excluindo navegação, login,
rede e decodificação das imagens. Movimento reduzido está habilitado.

| Cenário | Desktop: base → novo | Viewport móvel: base → novo |
| --- | ---: | ---: |
| Sem miniaturas | 0,80 → 0,30 ms | 0,80 → 0,30 ms |
| Com miniaturas sintéticas | 1,10 → 0,50 ms | 1,10 → 0,40 ms |
| A/A, mesma base nas duas versões | 0,70 → 0,80 ms | 0,70 → 0,70 ms |

A redução observada foi de aproximadamente 62–64% no viewport móvel. São medianas das
medianas por processo; a análise bootstrap reamostra as razões pareadas
dessas medianas. Os tempos são pequenos e sujeitos à resolução do relógio
e à variação do ambiente, também visível no A/A. Os intervalos pareados
das quatro comparações ficaram acima de 1; os dois controles A/A incluem 1. As contagens de elementos
e a identidade dos cartões são a evidência direta do trabalho evitado.

Todos os snapshots finais da fila coincidiram por SHA-256 após normalizar,
apenas numa cópia desconectada, dois valores transitórios: a fase temporal
da animação e os URLs privados `blob:` das imagens. Os caminhos das
miniaturas usadas na fixture substituem esses URLs na cópia. A página real
não é alterada por essa normalização; os testes funcionais verificam a
preservação da imagem e sua URL e a troca quando o campo de prévia muda.

O ambiente usa Linux e Chromium desktop com viewport 390 × 844. Não houve
medição em Android/iOS físico, bateria, FPS ou tempo total do aplicativo.
O resultado não é uma aceleração do motor de RIP.

## Verificação e distribuição

51 cenários de polling/UI aprovados, incluindo seis novos. Dos 42 cenários
comuns executados contra a base, 38 passaram e quatro demonstraram as
reconstruções evitadas; os 42 passam no painel novo. Nove verificações de
configuração de rede são executadas apenas no modo atual. O smoke de fila
também passou com 100 trabalhos, foco/rolagem, controles por teclado,
cancelamento preservando arte e viewports de 390 e 320 pixels. As provas
de 340 miniaturas e de upload em três contextos móveis passaram, incluindo
limites/limpeza do cache, quatro uploads reais para o backend temporário,
nomes iguais de aparelhos diferentes, logout e tentativas repetidas.

A suíte Python passou **1.877 testes**. `engine.py`, `prt.py` e `morph.py`
são idênticos à 0.8.42. A alteração é distribuída pelo servidor: atualizar
o AutoRIP no computador e recarregar o painel leva a melhoria ao celular.
O APK 0.2.2 e o agente 0.2.1 mantêm suas versões nativas.

```bash
python -m pytest -q
node tools/smoke_polling_ui.cjs /tmp/progress-polling
node tools/smoke_queue_ui.cjs /tmp/progress-queue
AUTORIP_POLLING_BASELINE=v0.8.42 node tools/smoke_polling_ui.cjs /tmp/progress-base
node benchmarks/benchmark_panel_jobs.cjs --baseline-ref v0.8.42 --repeat 5 --updates 50 --output /tmp/progress.json
node benchmarks/benchmark_panel_jobs.cjs --baseline-ref v0.8.42 --repeat 5 --updates 50 --thumbnails --output /tmp/progress-previews.json
node benchmarks/benchmark_panel_jobs.cjs --baseline-ref v0.8.42 --repeat 5 --updates 50 --aa --output /tmp/progress-aa.json
```

Requer Playwright/Chromium e aceita `AUTORIP_PYTHON`, `AUTORIP_CHROMIUM`,
`AUTORIP_PLAYWRIGHT_MODULE` e `AUTORIP_NO_SANDBOX=1` no ambiente gerenciado.
Dados: [sem imagens](panel-progress-benchmark.json),
[com imagens](panel-progress-preview-benchmark.json),
[A/A](panel-progress-control-aa.json), [análise](panel-progress-analysis.json),
[UI atual](panel-progress-polling.json),
[UI da base](panel-progress-baseline-polling.json) e
[fila](panel-progress-queue.json), [miniaturas](panel-progress-thumbnails.json)
e [upload móvel](panel-progress-uploads.json).
