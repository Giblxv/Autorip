# Revisão dos PRs 45, 46 e 47

Base: `adb602f`, após o release Windows 0.8.16 e a prévia móvel 0.2.0.
As propostas foram comparadas com a main atual antes da integração, preservando
os clientes móveis e as alterações do PR #52.

## PR 45: instalação real no Windows

O build já executa regressões e o aplicativo empacotado. A proposta acrescenta
uma prova distinta: executar o instalador Inno Setup e iniciar o EXE instalado.
Ela foi aproveitada com ajustes:

- Executa somente em runner Windows descartável do GitHub Actions, porque o
  instalador registra o aplicativo no Windows mesmo com diretório personalizado.
- Usa caminho de instalação com espaços e confere SHA-256 do EXE instalado contra
  o compilado, além de conferir a versão retornada pelo aplicativo.
- O estado do aplicativo é isolado por AUTORIP_HOME, offline, sem modo automático
  ou atualização. Não cria um trabalho de impressão.
- Obtém a URL real do log e exercita o fallback de porta ocupando a 8765; não
  assume que a API responderá sempre na primeira porta.
- Autentica e encerra pela API; em falha, termina a árvore de processos para não
  deixar o filho do bootloader segurando arquivos. Tenta desinstalar ao finalizar.

Build Windows passa a validar PRs/pushes relevantes. O job de compilação tem
permissão de leitura; publicação fica em job separado com escrita, somente para
tags v*. O executável e o instalador passam pelo mesmo processo antes da publicação.

## PR 46: CSP das miniaturas

A correção `img-src 'self' data: blob:` já estava na main. Reaplicar seu patch
antigo produziria conflito sem corrigir comportamento novo. Foram acrescentados
três testes semânticos dos cabeçalhos para HTML, estado e JavaScript do planejador:
blob fica restrito a imagens; scripts/default não recebem essa permissão, e
objetos/frames continuam bloqueados. Os testes não dependem de uma chamada JS
literal que pode mudar durante uma refatoração.

## PR 47: repetição de regressões

O orquestrador e seus testes foram aproveitados. Cada rodada inicia um pytest
novo; qualquer falha impede sucesso global. Foram acrescentados timeout por
rodada, validação de tipos e substituição atômica do relatório. Timeout e falha de
inicialização são registrados como falha, preservando o resultado das outras rodadas.

A matriz padrão continua rodando em todo PR: Linux/Windows, Python 3.10/3.12.
A opção `regression_15x` do workflow manual executa outras 15 rodadas completas
por sistema. Não é ativada automaticamente em todos os PRs, evitando multiplicar
o custo de alterações sem suspeita de instabilidade. Quando necessário:

```sh
gh workflow run tests.yml --ref main -f regression_15x=true
```

Quinze repetições da mesma suíte verificam estabilidade; não são quinze hipóteses
de otimização nem demonstram que o desempenho foi maximizado. As campanhas de
RIP permanecem registradas separadamente, com comparação de bytes e medições.

Checkout/setup-python/artifact foram atualizados para as versões principais
usadas na proposta, com credenciais Git não persistidas no checkout. Nenhuma
mudança de motor RIP, formato PRT, perfis, configurações ou aplicativos móveis
é feita por esta consolidação.

## PrintExp TCP

A verificação solicitada em paralelo está em [PRINTEXP-TCP.md](../PRINTEXP-TCP.md).
Há evidência de modalidades TCP, mas IP, porta, versão e protocolo da instalação
do usuário ainda são necessários. Não foi habilitado envio de trabalhos.

## Validação local

738 testes passaram em 80,17 s; a bateria focada teve 67 aprovações. O CLI
executou duas rodadas reais de sete testes, sem apresentar essa prova curta como
15 regressões completas. Planejador (nove cenários), consultas (23), fila e
miniaturas passaram novamente no Chromium. O smoke local v0.8.16 preservou
planejamento, uploads e bytes PRT/JPEG. [Dados e hashes](open-pr-validation.json).
