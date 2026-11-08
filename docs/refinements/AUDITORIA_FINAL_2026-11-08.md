# Auditoria e refinamento do AutoRIP — 8 nov. 2026

## Resultado

Foi criado um candidato local na branch `manus/autorip-refine`, baseada em `origin/main` (`e8106dfc15a5542703ea6b02a87ceaff4c03539a`). `main` não foi alterada e nada foi enviado ao GitHub. A branch preserva as integrações locais para revisão/CI, não é uma aprovação para publicar a versão em produção.

**Validação local final:** `python3 -m pytest -q -W error` — **189 passed**; `python3 -m compileall -q autorip autorip_gui.py tests tools` — passou; `python3 -m pip check` — sem dependências quebradas; Ruff (`--select F`) — passou; `git diff --check` — passou; `node --check` do JavaScript embutido no painel — passou. Bandit encontrou **0 achados médios/altos e 4 baixos**: dois `try/except` com continuação/ignorância deliberada, e o uso de subprocesso no instalador do atualizador após verificação SHA-256.

## PRs integrados ao candidato local

Os merges locais existentes incorporam #3, #6, #13–#28, exceto #9 e #12, que foram tratados por port/testes locais: #9 teve seus testes de limpeza de downloads parciais reaplicados; #12 teve o tratamento de ICC embutido portado com limite de 16 MiB, preservação de alfa e rejeição de perfis inválidos/incompatíveis. Os PRs #18–#28 incorporam ainda matriz Windows/Linux, isolamento de etiquetas, fallback sem hard-link, sincronização do PRT, reserva de espaço, remoção de executáveis da árvore corrente, validação de versão/tag, revogação de sessões e template de revisão. A recuperação de outbox foi complementada para persistir os destinos originais de notificação, mesmo quando um canal está temporariamente desativado.

Após auditoria dos PRs novos, também foram portados ao candidato, com ajustes próprios: **#33** (worker continua após entrada removida), **#34** (asset deve ser da release/repositorio canônicos; redirects só para CDNs autorizadas), **#35** (toggle de modo automático persiste antes de confirmar) e **#38** (falha esperada em um anexo Trello não interrompe os demais, mas erro de publicação continua propagando). **#37** foi portado com correções: CSP permite `blob:` para imagens autenticadas e a interface limpa fila/estado ao perder a sessão.

Na rodada seguinte, **#40, #41 e #43** foram auditados separadamente e integrados localmente com correções combinadas: #40 tolera remoção de arquivo entre `listdir` e `stat`; #41 preserva origem e journal ilegível, bloqueando RIP potencialmente duplicado e deduplicando alertas no servidor e watcher; #43 impede encerramento por inatividade durante modo automático, Trello, fila, job/arte em recuperação ou journal pendente. O estado `locked` de #37 agora atualiza atividade somente após validar o Host, sem expor dados; a verificação de idle também considera a pasta `.autorip_processing`, para não perder jobs antigos fora do histórico de 50 entradas. #41 foi mesclado com a proteção de corrida do #40, em vez de integrar o head isolado que a removeria.

O tratamento de erros do Trello foi limitado a `OSError`/`ValueError`, evitando esconder falhas de publicação ou bugs genéricos.

Outras correções encontradas durante os testes: leituras de arquivos sem fechamento explícito nos testes, atualizador e rotas de UI/thumb/logo; race na emissão de token durante trocas concorrentes de senha; validação textual estrita de Host (incluindo Host duplicado); upload escolhido antes do login preservado para envio depois da autenticação; e preflight de disco que reserva o pico de **duas cópias do PRT + 128 MiB**, necessário no fallback de publicação por staging.

## PRs deliberadamente não integrados

| PR | Decisão | Motivo técnico |
|---|---|---|
| #29 | Adiado | Corrida reproduzível: uma miniatura pode ser recriada depois que o PRT é excluído. O JPEG por ID pode continuar acessível fora do histórico limitado de jobs. |
| #30 | Adiado | A gravação publica duas miniaturas em operações separadas; falha na segunda pode deixar previews por ID e por nome divergentes, sem rollback. |
| #36 | Adiado | Há uma janela entre publicar anexo e persistir o recibo Trello; queda/falha pode duplicar a importação. O ledger também expira IDs antigos ao atingir o limite. |
| #32, #39 e #42 | Não mesclar | São drafts agregadores de testes/integração, não unidades de produção; carregam alterações combinadas e não substituem revisão de cada PR funcional. |

As conclusões dos PRs #29/#30/#36 devem ser corrigidas nos próprios branches antes de uma futura adoção; não foram implementados atalhos que poderiam mascarar perda/duplicação.

## Limitações que permanecem

A suíte e as imagens de referência são sintéticas. **Não houve validação física com PrintExp/Hoson**, firmware, impressora, tinta ou ICC proprietário; qualquer alteração de cor/PRT requer amostra controlada antes de produção. A execução local foi Linux; não foi produzido um binário Windows nesta rodada. Checks remotos de PRs individuais foram consultados, mas não equivalem a um build Windows do candidato final. Não foi feita publicação, merge remoto nem push.
