# Segunda fase de análise profunda e refinamento contínuo

**Data de início:** 2026-11-09 02:47 UTC  
**Branch:** `phase2/continuous-refinement-2026-11-09`  
**Política:** nenhuma alteração em `main`, nenhum force-push, nenhum merge automático e nenhuma validação física presumida.

## Estado inicial

O repositório foi clonado a partir de `Giblxv/Autorip` com `main` apontando para `1097665`. A revisão das releases encontrou `v0.8.5` a `v0.8.12`, com `v0.8.12` como latest. O issue aberto #31 registra que a integração cruzada e a compatibilidade física PRT ainda exigem aprovação humana e ensaio controlado; esse bloqueio foi preservado.

A suíte de linha de base passou com **197 testes** antes da rodada 1.

## Rodada 1 — AR-016

**Achado:** metadados `dpi` ausentes, inválidos, não finitos ou negativos podiam contaminar a geometria natural da arte porque o código só substituía zero por 300.

**Mudança:** `_safe_source_dpi` passou a aceitar apenas DPI finito e positivo, usando 300 por eixo para valores ausentes ou corrompidos. Valores positivos válidos permanecem iguais. Foram adicionados testes unitários para `None`, zero, negativo, `NaN`, infinito, texto inválido, string numérica e inteiro positivo.

**Arquivos:** `autorip/engine.py`, `tests/test_engine.py`, `docs/refinements/AR-016.md`.

**Evidência:** teste focado `43 passed`; suíte completa **204 passed em 39,92 s**; `git diff --check` passou.

**Risco:** o fallback protege entradas corrompidas, mas não prova que um DPI positivo incorreto representa a mídia física real. Não houve alteração de PRT, canais, branco, ICC, meio-tom, mirror ou geometria explicitamente informada.

## Rodada 2 — AR-017

**Achado:** o atualizador validava o host dos redirecionamentos, mas aceitava qualquer caminho no `github.com`, embora o fluxo esperado fosse baixar somente assets de release do próprio repositório.

**Mudança:** redirecionamentos que permanecem no GitHub agora exigem o caminho `/Giblxv/Autorip/releases/download/`, sem porta, query ou fragmento; as CDNs permitidas continuam aceitas. Foram adicionados testes para destinos válidos e caminhos genéricos ou adulterados.

**Arquivos:** `autorip/updater.py`, `tests/test_updater.py`, `docs/refinements/AR-017.md`.

**Evidência:** teste focado `43 passed em 0,25 s`; `python -m compileall -q autorip tools` passou; `git diff --check` passou.

**Risco:** a mudança não foi exercitada contra servidor real de redirecionamento neste ambiente; a validação do handler foi feita por testes de URL. A conferência SHA-256 continua obrigatória.

## Bloqueios mantidos

A compatibilidade física com PrintExp/Hoson, a validação de branco/canais/ICC/meio-tom/mirror e o envio real à impressora continuam fora do que pode ser afirmado por testes automatizados neste ambiente. Releases e merges permanecem sujeitos à revisão humana.

## Referências

[1]: https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html "Pillow Image file formats"
[2]: https://github.com/Giblxv/Autorip/issues/31 "Autorip issue 31 — integração cruzada e critérios de validação"
[3]: https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases "GitHub About releases"
