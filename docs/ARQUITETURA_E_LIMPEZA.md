# Auditoria e limpeza da main

## Proposta preservada

A main continua organizada em quatro responsabilidades: núcleo RIP e PRT (`autorip/engine.py`, `morph.py`, `prt.py`), operação local (`config.py`, `paths.py`, `watcher.py`, `prints.py`), painel e planejamento (`server.py`, `layout.py`, `sheet_nesting.py`) e integração opcional com o PrintExp, mobile e serviços externos.

Os módulos opcionais não foram removidos apenas por serem opcionais. `bgremove`, os backends experimentais, integrações, atualização e mobile permanecem porque têm documentação, testes ou workflows próprios. Removê-los agora quebraria capacidades declaradas na interface e no README.

## Removido da árvore atual

- `benchmarks/campaign_runs/`: relatórios, snapshots, imagens, PRTs e logs gerados de campanhas antigas. Eram aproximadamente 20 MB e não participavam da execução do AutoRIP. Os scripts reprodutíveis continuam em `benchmarks/`.
- `backup/AutoRIP-Windows-e5f5022/`: referências de distribuição; binários devem ser obtidos por Actions/Releases com SHA-256.
- `RELEASE_NOTES_0.8.13.md` e `RELEASE_NOTES_0.8.14.md`: duplicatas antigas das notas em `docs/releases/`.

As referências documentais aos resultados brutos foram convertidas para indicações de artefato histórico não versionado. Isso evita links quebrados e deixa claro que a evidência pode ser reproduzida pelos scripts de benchmark.

## Refatorações aplicadas

- Remoção de imports mortos em CLI, servidor, agente e nesting.
- Uso de `collections.abc.Iterable` nas anotações de tipo.
- Build online e offline alinhados: o agente PrintExp também é compilado e suas dependências são baixadas no pacote offline.
- `.gitignore` passou a bloquear campanhas geradas e backups.
- Novos assets do instalador usam composição psicodélica técnica em CMYK, sem texto gerado por imagem, mantendo o texto nativo do Inno Setup legível.

## Itens deliberadamente mantidos

- O ICC de teste permanece porque testes de cor dependem dele; removê-lo exigiria trocar os testes por uma fixture reproduzível e alteraria a validação de pixels/PRT.
- `autorip/server.py` continua grande por concentrar HTTP local, fila, autenticação e endpoints. Uma divisão mecânica em vários arquivos teria alto risco de alterar estado compartilhado; a próxima refatoração recomendada é extrair primeiro o roteamento HTTP e os handlers por domínio, com testes de contrato.
- APIs antigas de `autorip.nesting` permanecem por compatibilidade, embora o painel use `sheet_nesting`.

## Critério de aceitação

A limpeza é considerada segura quando `python -m pytest -q` passa, os builds Windows online/offline mantêm os mesmos artefatos esperados e nenhum link para arquivo removido permanece na documentação.
