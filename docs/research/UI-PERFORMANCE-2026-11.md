# Pesquisa: desempenho da interface no desktop e no app

## Objetivo

Investigar melhorias para a responsividade do painel AutoRIP no Windows, Android e iOS sem confundir desempenho da interface com velocidade do motor RIP. Este documento registra o que foi verificado no código, o que é hipótese e como validar cada proposta.

## O que já está comprovado no repositório

**Fato verificável:** o painel suspende os timers de estado, impressões e hot folder quando a página fica oculta e atualiza ao retornar. A implementação está em `autorip/ui/index.html`, e a documentação de validação está em `docs/refinements/PANEL-PERFORMANCE.md`.

**Fato verificável:** a fila reutiliza cartões que não mudaram e, durante uma atualização de progresso, altera somente os elementos necessários. `docs/refinements/PANEL-PROGRESS.md` registra testes sintéticos com 100 cartões e deixa claro que os tempos medidos não representam uma aceleração universal do aplicativo nem do RIP.

**Fato verificável:** o cliente Android entrega o painel web por WebView/Capacitor, enquanto o cliente iOS usa Flutter com `webview_flutter`, que apresenta `WKWebView`. Portanto, uma otimização do painel pode alcançar as duas plataformas, mas uma otimização nativa precisa ser medida separadamente.

## Ideias priorizadas

### 1. Instrumentar a responsividade real antes de alterar o pipeline

**Por que funciona para o público:** permite atacar a ação que realmente parece lenta para quem envia uma arte, acompanha o RIP ou controla a fila, em vez de otimizar uma rotina que o usuário não percebe.

**Fato verificável:** o INP mede a latência das interações de clique, toque e teclado até a próxima pintura; a referência de boa responsividade é até 200 ms no percentil 75. [1]

**Hipótese:** registrar localmente, sem enviar dados para fora do computador, a duração das ações `Enviar arquivos`, `Calcular encaixe`, `Pausar/Retomar`, `Cancelar`, abertura de diálogos e login revelará se o custo dominante é JavaScript, layout, rede ou backend.

**Proposta de validação:** adicionar uma pequena camada de medição somente em modo de diagnóstico, com marcações `performance.mark()`/`performance.measure()`, limite de amostras e redaction de nomes de arquivos, senhas, tokens e endereços. O critério de aceite é produzir um relatório reproduzível para as jornadas acima sem alterar o comportamento normal.

### 2. Aplicar contenção somente a blocos grandes e não críticos

**Por que funciona para o público:** reduz trabalho de layout e pintura quando há muitas mensagens, cartões ou seções fora da área visível, preservando a resposta da fila que está sendo acompanhada.

**Fato verificável:** `content-visibility: auto` pode adiar layout e pintura de conteúdo fora da viewport; `contain-intrinsic-size` evita que a área reservada colapse ou cause saltos de rolagem. A mesma documentação alerta que o conteúdo permanece na árvore de acessibilidade e que elementos ocultos precisam ser tratados com cuidado. [2]

**Hipótese:** aplicar a regra a itens de ajuda e linhas estáticas longas pode reduzir trabalho de renderização; aplicar diretamente a cartões com foco, status ao vivo ou miniaturas pode piorar acessibilidade ou introduzir mudanças visuais.

**Proposta de validação:** começar por uma classe explícita em seções estáticas, com tamanho intrínseco calibrado por teste visual. Não aplicar à fila ativa, a regiões `aria-live`, ao cartão focado ou a diálogos abertos. Comparar DOM, foco, rolagem, leitor de tela e custo de renderização antes/depois.

### 3. Medir o app Android em dispositivo, não inferir do Chromium desktop

**Por que funciona para o público:** identifica travamentos que só aparecem durante inicialização, rolagem ou retorno do WebView em telefones com memória e CPU diferentes do computador de desenvolvimento.

**Fato verificável:** a documentação Android recomenda medir startup, jank e memória com Macrobenchmark, Perfetto e Android Studio Profiler. Ela também define jank como quadros que não terminam no tempo disponível e recomenda observar tempos de renderização por jornada. [3]

**Hipótese:** o app pode ter maior custo no primeiro carregamento do bundle, na criação da WebView ou na decodificação de miniaturas; o repositório não contém evidência suficiente para afirmar qual deles domina em aparelhos reais.

**Proposta de validação:** criar um cenário de benchmark para abrir o app, conectar ao servidor local, abrir a fila com 100 trabalhos, rolar e retornar do background. Registrar cold/warm start, P95/P99, quadros lentos, memória e bateria em pelo menos um aparelho de entrada e um intermediário. Sem dispositivos físicos, o resultado deve ser marcado como não medido.

### 4. Preservar a arquitetura híbrida e evitar uma reescrita prematura

**Por que funciona para o público:** mantém a mesma interface no painel, Android e iOS, reduzindo divergências e evitando que uma reescrita introduza diferenças em autenticação, fila ou conexão local.

**Fato verificável:** o README e os arquivos `mobile/` e `mobile_ios/` mostram que o Android e o iOS usam superfícies distintas para abrir o painel, mas ambos dependem da interface web atual.

**Hipótese:** os ganhos mais seguros estão em reduzir trabalho do painel e medir as jornadas nativas antes de trocar WebView por uma UI duplicada.

**Critério de decisão:** só considerar reescrita nativa se um benchmark físico reproduzir um gargalo que não possa ser resolvido no painel ou na configuração do WebView, e se a paridade funcional puder ser testada.

## Ordem recomendada

1. Instrumentação local e cenário de benchmark.
2. Correções comprovadas pelo cenário, começando por trabalho de DOM/layout.
3. Contenção limitada para conteúdo estático, com teste de acessibilidade.
4. Otimizações nativas Android/iOS somente quando houver evidência específica da plataforma.

A ideia mais promissora é a instrumentação local combinada com um benchmark de jornadas. Ela evita suposições, aproveita as otimizações já existentes e transforma futuras mudanças em decisões comparáveis. Não há base suficiente para afirmar um percentual de ganho antes da medição.

## Revisão crítica

### Problemas encontrados

- Seria incorreto repetir que o painel ainda reconstrói toda a fila: o código já preserva cartões e progresso em atualizações incrementais.
- Seria exagerado prometer que `content-visibility` produz um ganho fixo; o efeito depende da quantidade de conteúdo fora da viewport, do navegador e do dispositivo.
- Os benchmarks atuais do painel são controlados em Chromium e não provam FPS, bateria, memória ou desempenho em Android/iOS físicos.
- A expressão “aceleração por hardware” é vaga e não deve ser usada como solução sem perfil de renderização.
- A arquitetura móvel não é uniforme: Android e iOS têm integrações nativas diferentes apesar de carregarem o mesmo painel.

### Versão final corrigida, pronta para uso

A próxima etapa de desempenho deve começar por medir as jornadas que o usuário percebe: abertura, login, envio de arquivos, cálculo de encaixe, acompanhamento da fila e pausa/retomada de trabalhos. O painel já evita polling em segundo plano e já reutiliza cartões estáveis; portanto, a pesquisa deve procurar trabalho restante, não repetir essas melhorias.

A recomendação técnica é adicionar medição local e reproduzível, sem enviar dados do usuário, e comparar as alterações em desktop e em dispositivos móveis. Para o Android, a validação deve usar Macrobenchmark, Perfetto e o profiler de memória. Para o iOS, deve separar o tempo do Flutter, da `WKWebView`, da rede local e do painel. Uma medição feita apenas em Chromium desktop não deve ser apresentada como resultado de telefone.

Depois da medição, pode-se testar contenção de layout em conteúdo estático fora da viewport. A fila ativa, os cartões focados, as regiões de status e os diálogos devem ficar fora da primeira aplicação até que foco, rolagem, acessibilidade e miniaturas estejam cobertos por testes. Qualquer número de ganho deve ser publicado somente com o cenário, dispositivo, versão do navegador e intervalo de incerteza.

## Referências

[1]: https://web.dev/articles/inp "Interaction to Next Paint — web.dev"
[2]: https://web.dev/articles/content-visibility "content-visibility: the new CSS property that boosts your rendering performance — web.dev"
[3]: https://developer.android.com/topic/performance/measuring-performance "Measure app performance — Android Developers"
[4]: https://github.com/Giblxv/Autorip "AutoRIP — repositório e documentação do projeto"
