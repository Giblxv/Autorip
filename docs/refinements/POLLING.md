# Painel: consultas agrupadas, respostas antigas e linhas estáveis

Base: `0298da6`, após a etapa de [miniaturas](THUMBNAILS.md).
Esta continuação melhora o uso prolongado do painel. O renderizador, os formatos
PRT e os intervalos de estabilidade das artes permanecem iguais à base.

## Consultas e sessão

Estado, fila de impressão e hot-folder compartilham um coordenador de consulta
por recurso. Um tick periódico reutiliza o trabalho em andamento. Um pedido
explícito de atualização invalida aquela fotografia e agenda uma nova consulta;
pedidos repetidos enquanto ela está pendente se agrupam na mesma atualização.
As ações bem-sucedidas e o login pedem essa atualização, evitando perder uma
mudança quando já havia uma consulta em voo.

A API associa cada resposta à sessão que fez o pedido. Respostas de sessões
antigas e respostas após encerrar o painel são descartadas. Um 401 da sessão
atual limpa imediatamente filas, miniaturas, dados de configuração e saída do
agente. Um 404, 500 ou erro de conexão informa a falha sem apagar o login.
Configurações também verificam a ordem dos pedidos e se o diálogo continua aberto.

Os intervalos continuam em um segundo para estado e três segundos para listas.
O heartbeat não é suspenso em abas ocultas, pois participa da detecção de uso do
servidor. Esta etapa não reduz a frequência normal de atualização.

## Atualização das listas

Linhas de hot-folder e PRT são reutilizadas pelo nome e assinatura dos dados.
Uma alteração substitui somente a linha afetada; remoção e reordenação mantêm
os outros nós conectados. O foco do teclado é restaurado quando uma mudança ou
movimento de nó o remove. O indicador de próximo PRT muda sem reconstruir a
linha que assumiu a primeira posição.

Fotografias idênticas da hot-folder encerram cedo. Na impressão, preservam-se
os nós e atualiza-se apenas o texto de idade que realmente mudou: antes, uma
lista sem alterações podia exibir “agora” indefinidamente. As prévias das linhas
preservadas continuam decodificadas e conectadas. Os mapas descartam linhas que
saem da resposta, e a troca de sessão ou encerramento limpa suas referências.
Não há virtualização ou novo limite de itens nesta etapa.

Após confirmação bem-sucedida do encerramento, o painel cancela seus timers e
consultas pendentes, limpa miniaturas/referências e ignora callbacks tardios.
A tela de saída permanece estável sem continuar consultando elementos removidos.

## Prova controlada no navegador

O smoke usa Chromium/Playwright, servidor e dados temporários: 100 trabalhos,
dois PRTs e duas artes na hot-folder. As respostas em voo são seguradas por
barreiras explícitas, incluindo 401, falhas, troca de sessão e mutação durante
uma consulta. A comparação da base substitui somente o HTML pelo de `0298da6`;
ambos os casos usam o mesmo backend de teste, sem impressora ou dados reais.

| Cenário | HTML da base | Refinado |
| --- | ---: | ---: |
| Mutações childList na hot-folder, 20 consultas idênticas | 60 | 0 |
| Pedidos na rajada: uma consulta + 12 ticks + 8 atualizações explícitas | 21 | 2, sequenciais |
| Pedidos após encerrar, janela de 3,3 segundos com timers ativos | 5 | 0 |
| Provas de comportamento | 4/23 aprovadas | 23/23 aprovadas |

O teste também verifica foco e nós após alterar/reordenar listas, prévias
preservadas, atualização da idade sem substituir linhas, zero escritas no DOM
da fila de impressão em 20 consultas idênticas, sessão nova protegida de 401 e
dados antigos, limpeza imediata em 401 atual, falhas 404/500/rede sem logout,
diálogo fechado, remoção completa do aviso de login e descarte de uma lista anterior à confirmação de impressão.
Nenhum erro JavaScript foi observado na versão refinada. As reprovações da base
são cenários de regressão, não uma contagem de defeitos independentes.

Essas contagens descrevem os eventos e a janela controlados. Não são um fator
de aceleração do RIP nem uma medição de CPU/RAM total. O relatório registra a
versão do navegador e o SHA-256 do HTML; os tempos do motor seguem documentados
nas campanhas anteriores.

## Validação e reprodução

- 382 regressões Python aprovadas; detalhes de tempo na validação do PR.
- Smoke completo de controles com 100 trabalhos: teclado, pausa/retomada,
  cancelamento preservando arte, capacidade, preparação, rolagem e mobile 390/320.
- Smoke de miniaturas: 340 imagens, 5 requisições iniciais, 24 após a navegação
  prevista, máximo de quatro simultâneas, limites de cache/TTL e troca de sessão.
- Launcher local v0.8.14: login, upload, PRT e encerramento; versão do instalador consistente.

[Dados estruturados: base e refinado](../../benchmarks/campaign_runs/2026-11-09-polling/browser-results.json).

```bash
python -m pytest -q
# Opcional: requer Node, Playwright e Chromium de desenvolvimento.
AUTORIP_PYTHON=.venv/bin/python node tools/smoke_polling_ui.cjs /tmp/polling-ui
AUTORIP_PYTHON=.venv/bin/python AUTORIP_POLLING_BASELINE=0298da6 node tools/smoke_polling_ui.cjs /tmp/polling-baseline
```

O modo de base registra reprovações esperadas no JSON e encerra normalmente;
o modo atual retorna erro se alguma prova falhar. Os seletores opcionais de
Python, Chromium e Playwright seguem os outros smokes de UI. Não há nova
dependência de produção ou migração de configurações.
