# Campanha de desempenho de 12/11/2026

Campanha nova: prazo de 12/11/2026 às 22h de São Paulo (13/11 às 01h UTC) ou 100 rodadas consecutivas sem novo ganho confirmado. A contagem não reutiliza campanhas anteriores. O ganho de planejamento abaixo reiniciou a sequência em zero.

O encaixe evita materializar dataclasses de candidatos cuja altura arredondada não poderia vencer a melhor folha atual. Em 112 combinações, layouts/SVGs e entradas permaneceram idênticos; num exemplo de oito peças, as cópias caíram de 240 para 16. Exploração e confirmação em workers novos repetiram o ganho de uma peça (cerca de 1,6× na confirmação). As cargas maiores e o A/A foram ruidosos: não se afirma ganho geral em folhas grandes. O primeiro driver inclui a medição de memória fora do cronômetro; o segundo só permite omiti-la. 1125 testes e o smoke do aplicativo passaram.

A fase RIP combina hipóteses ainda não testadas com uma busca limitada de trabalhadores, altura de tira e limiar de paralelismo. O preflight identificou 268 propostas elegíveis, incluindo 227 planos de execução distintos. Hashes de corpos e ASTs evitam aliases por comentários/espaços; planos equivalentes e configurações inertes não contam. Propostas conhecidas como inadequadas ficam excluídas. São 30 PRTs de correção e 12 cargas cronometradas, incluindo 6000 pontos de largura, com 15 pares, confirmação e controle A/A. Cada ganho exige regressões completas antes de alterar o líder; a guarda contra a base inicial evita acumular regressões. Erros não são usados para completar a meta.

Os resultados finais serão adicionados ao encerrar. A execução fica no worktree dedicado e depende de o ambiente continuar ativo; checkpoints permitem retomada. Nenhum perfil ICC proprietário é incluído nesta evidência.

## Correção da contagem antes da retomada

O filtro de planos foi estendido às famílias antigas (tiras, pipelines, limiares, orçamento e estimativas por pixel), além da grade nova. O relatório bruto de sete rodadas é preservado em `before-plan-filter/`: a alteração de limiar que não mudava nenhum plano foi retirada da sequência, restando seis rejeições válidas desta mesma campanha. A oitava rodada parcial não conta. A retomada começa em seis, e um aceite posterior continua zerando a sequência normalmente. `adjudication.json` permite reproduzir a correção por hashes e planos reais.

A cobertura das 12 cargas confirmou que os atalhos de raio subpixel e canal inteiramente saturado não eram acionados; eles foram excluídos. O caminho de cópia RGBA foi acionado e continua elegível. A preparação revisada identificou 251 propostas elegíveis, com 231 planos de escalonamento distintos; `preflight-initial.json` conserva a preparação anterior. Passaram 1126 testes completos e cinco testes offline das barreiras de publicação.
