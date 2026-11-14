# Artefatos de distribuição e backups Windows

Os arquivos de distribuição `AutoRIP.exe` e `AutoRIP_Setup.exe` não devem ser commitados na árvore fonte. Eles têm dezenas de MiB e fazem checkout, revisão e downloads do repositório mais pesados.

## Onde encontrar novas compilações

- **Actions → Build Windows:** em uma execução concluída com sucesso, procure o artifact `AutoRIP-Windows-<commit>`. Os artifacts têm prazo de retenção (atualmente 14 dias no workflow).
- **Releases:** uma tag `v*` aciona o build e publica os binários e `SHA256SUMS.txt` na release, se o workflow concluir.
- **Integridade:** confira SHA-256 dos executáveis usando o manifesto publicado junto da mesma compilação.

## Histórico de backup

Backups e binários de distribuição não fazem parte da árvore fonte. As compilações devem ser obtidas pelos artifacts do GitHub Actions ou pelas Releases, com SHA-256 publicado junto. O histórico Git antigo pode continuar contendo objetos removidos; isso não afeta o checkout atual.

## Critérios para releases

1. Testes automatizados sem falhas, preferencialmente Linux e Windows.
2. Revisão manual das mudanças de PRT, branco, canais e ICC.
3. Teste físico controlado com PrintExp/Hoson antes de adotar a compilação em produção.
4. Conferência de SHA-256 e possibilidade de rollback.
