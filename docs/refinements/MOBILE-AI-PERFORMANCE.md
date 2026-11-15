# Contas de IA, conexão móvel e desempenho — 2026-11-15

Base: `5827ec9` (AutoRIP 0.8.28 / Mobile 0.2.1). Alterações locais na branch
`perf/rip-apk-2026-11-15`; sem nova versão ou publicação de artefatos.

## Funcionalidade

O cadastro de [contas de IA](../AGENTES-IA.md) aceita vários registros do mesmo
provedor, sem teto de quantidade. Gemini, DeepSeek, Manus, OpenAI, Anthropic,
Grok, Perplexity e OpenRouter têm adaptadores próprios ou usam chat completions.
As contas são paginadas em grupos de 50 somente na edição. As chaves ficam
ocultas nas respostas HTTP, são preservadas quando o campo está vazio e se
alternam entre consultas. A configuração Anthropic anterior permanece compatível
e participa da rotação. Não há consultas automáticas ao cadastrar chaves.

Manus usa `task.create` v2, cria uma tarefa privada e devolve a URL; não apresenta
uma tarefa recém-criada como resultado pronto. Modo offline, bloqueio de
redirects e contexto técnico sem chaves, nomes de arquivos ou logs permanecem.
Os testes usam credenciais fictícias e respostas simuladas, sem consultas reais
pagas aos provedores.

O fluxo [Conectar celular](../GUIA-APPS-MOVEIS.md) lista as interfaces privadas,
ativa um listener no IPv4 escolhido e na mesma porta do painel e gera um QR
contendo só a URL. A senha continua necessária no telefone. O listener pode ser
desativado sem encerrar o servidor principal. Configuração salva, falha de bind,
rollback de persistência e desligamento pelo próprio listener têm regressões.

## Medições

Ambiente Linux, Python 3.12, quatro CPUs disponíveis pela quota do ambiente.
Os números não representam uma medição no computador Windows do usuário.

| Caso | Referência | Alteração | Resultado observado |
| --- | ---: | ---: | --- |
| JavaScript solicitado ao abrir o app | 32.656 B | 2.432 B | 92,55% menos bytes iniciais |
| Corpo de três consultas sem mudança | 14.359 B/rodada | 0 B/rodada | 304 autenticado, sem corpo |
| Construções ICC nos workers, 32 faixas com perfil acima de 2 MiB | 32/trabalho | 4/trabalho | Uma construção por worker |

O leitor de QR faz três pedidos de módulos adicionais apenas ao abrir a câmera.
A redução de JavaScript inicial não é uma redução equivalente no tamanho do
APK nem uma medição de tempo de abertura num Android físico. O histórico renderiza
cinco itens mesmo com 10.000 entradas; uma falha de gravação do histórico não
impede conectar.

Os endpoints de acompanhamento continuam gerando e autenticando suas respostas
no servidor. O ETag elimina o corpo sem mudanças e permite reutilizar no cliente
o JSON já interpretado. Cabeçalhos e pedidos ainda trafegam. Recuperação de rede,
troca de sessão, respostas obsoletas, idade relativa das impressões e atualização
de trabalhos continuam verificadas.

O benchmark de RIP completo usa três execuções por grupo (base, alteração e
controle da base), ordem embaralhada, aquecimento e nove grupos medidos em cada
caso. Foram comparados 120 PRTs e seus metadados, todos idênticos.

| RIP completo | Base, mediana | Alteração, mediana | Controle, mediana |
| --- | ---: | ---: | ---: |
| RGB, ICC maior que o cache | 273,5 ms | 252,2 ms | 267,5 ms |
| RGBA com branco, ICC maior que o cache | 537,8 ms | 547,0 ms | 571,5 ms |
| RGB com perfil normal | 201,6 ms | 204,4 ms | 199,0 ms |
| Imagem pequena serial | 36,6 ms | 36,5 ms | 35,8 ms |

Os intervalos de 95% das razões entre base e alteração incluem 1 nos quatro
casos: o tempo total não demonstrou ganho consistente neste ambiente. A melhoria
confirmada é evitar reconstruções de transformações ICC por faixa quando o
perfil excede o cache ou o cache está desligado. O contexto privado de cada
worker é liberado ao terminar o trabalho, preservando a política de memória e
os pixels. Não há promessa de aceleração universal.

## Reprodução e limites

```bash
python -m pytest -q
python benchmarks/benchmark_source_workers.py --baseline-ref 5827ec9 --pairs 9 --output /tmp/source-workers.json
node tools/smoke_polling_ui.cjs /tmp/polling
node tools/smoke_connections_ai.cjs /tmp/connections-ai
node tools/smoke_mobile_startup.cjs /tmp/mobile-startup
node tools/smoke_visual_ui.cjs /tmp/visual
node tools/smoke_queue_ui.cjs /tmp/queue
node tools/smoke_nesting_ui.cjs /tmp/nesting
```

Os smokes usam Playwright/Chromium e aceitam `AUTORIP_PLAYWRIGHT_MODULE`,
`AUTORIP_CHROMIUM`, `AUTORIP_PYTHON` e `AUTORIP_NO_SANDBOX=1` para o ambiente
gerenciado. A suíte final passou com 1.307 testes. Foram aprovados 45 cenários de polling, nove de planejamento, os
fluxos de fila, layout responsivo, conexão e edição de contas. O fluxo de contas
no navegador salvou 141 registros e confirmou campos de senha e redação das
chaves. O teste do listener usa HTTP real com uma interface LAN simulada.

`npm run build` e `npx cap sync android` passaram; o plugin nativo BarcodeScanner
continua registrado. Esta rodada não gerou EXE/APK nem executou câmera física,
firewall Windows ou conexão com um telefone real. A API Manus foi conferida na
documentação oficial; cada serviço ainda precisa de chave/modelo válidos e cota
para uma consulta real. Evidências locais: `/workspace/autorip-review/rip-apk-2026-11-15/`.
