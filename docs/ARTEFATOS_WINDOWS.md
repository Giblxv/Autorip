# Artefatos de distribuição e backups Windows

Os arquivos de distribuição `AutoRIP.exe` e `AutoRIP_Setup.exe` não devem ser commitados na árvore fonte. Eles têm dezenas de MiB e fazem checkout, revisão e downloads do repositório mais pesados.

## Onde encontrar novas compilações

- **Actions → Build Windows:** em uma execução concluída com sucesso, procure o artifact `AutoRIP-Windows-<commit>`. Os artifacts têm prazo de retenção (atualmente 14 dias no workflow).
- **Releases:** uma tag `v*` aciona o build e publica os binários e `SHA256SUMS.txt` na release, se o workflow concluir.
- **Integridade:** confira SHA-256 dos executáveis usando o manifesto publicado junto da mesma compilação.

## Histórico de backup

Os dois binários do caminho `backup/AutoRIP-Windows-e5f5022/` foram retirados apenas da **árvore atual**, em proposta sujeita à aprovação. Não houve reescrita ou limpeza do histórico Git; continuam recuperáveis do commit histórico que os continha. O checkout normal de branches novas fica menor, mas o tamanho do histórico completo do Git não é automaticamente reduzido.

**Antes de fazer merge:** confirme que não há dependência operacional de obter esses backups pelo botão "Download ZIP" da branch principal. Caso precise preservá-los como downloads diretos, publique primeiro os artefatos em Releases ou outro repositório de binários.

## Critérios para releases

1. Testes automatizados sem falhas, preferencialmente Linux e Windows.
2. Revisão manual das mudanças de PRT, branco, canais e ICC.
3. Teste físico controlado com PrintExp/Hoson antes de adotar a compilação em produção.
4. Conferência de SHA-256 e possibilidade de rollback.
