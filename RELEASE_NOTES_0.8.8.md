# AutoRIP v0.8.8

## Destaques

- Integração Linux para PC servidor dedicado com Ubuntu Desktop LTS.
- Instalador `systemd` com AutoRIP iniciado automaticamente no boot.
- Compartilhamentos Samba para hot folder, saída PRT, concluídos e erros.
- Acesso remoto por XRDP e administração por Cockpit, restritos à rede local.
- Firefox incluído na imagem automática para Trello e demais aplicativos web.
- Gerador de ISO automática UEFI/BIOS para instalação em SSD USB.
- Perfil ICC configurável no servidor Linux sem embutir o perfil na ISO.

## Trello

- Varredura periódica de cards novos.
- Suporte a várias listas de entrada.
- Seleção de extensões permitidas.
- Filtro por padrões de nomes de anexos.
- Intervalo de scanner configurável entre 10 segundos e 1 hora.
- Ledger persistente de anexos processados para evitar redownload após reinício.
- Falha isolada de um anexo não bloqueia os demais.
- Tokens não são colocados em URLs ou logs.

## Confiabilidade e segurança

- Validação estrita de Host e proteção contra DNS rebinding.
- Proteção de sessão e fila contra acesso anônimo.
- Recuperação segura de journals ilegíveis ou symlinks.
- Proteção contra arquivos removidos durante varredura.
- Publicação PRT atômica e fail-closed em filesystems incompatíveis.
- Reserva de espaço para o pico de duas cópias temporárias.
- Tags de release e downloads do atualizador validados.
- Testes com warnings tratados como erros.

## Validação

- 190 testes passando.
- `compileall`, Ruff, sintaxe JavaScript e Bash validados.
- Pacote Linux gerado e testado com checksum SHA-256.
