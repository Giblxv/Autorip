# AutoRIP v0.8.14

## Destaques

Esta versão integra a identidade visual psicodélica do painel com melhorias de operação da fila. A interface agora mostra os arquivos disponíveis na hot folder, permite iniciar uma arte manualmente e oferece controles de pausa, retomada e cancelamento por trabalho.

A pausa é cooperativa e acontece entre tiras de processamento. Ela não publica PRT parcial; a retomada recomeça o RIP desde o início seguro. O cancelamento preserva a arte na pasta de erros para revisão. A semântica de PRT, canais, branco, ICC, meio-tom, mirror e geometria não foi alterada por esses controles.

Uploads manuais não possuem mais quota artificial de bytes. Permanecem a validação do arquivo, o limite de 80 milhões de pixels, o espaço livre mínimo de 128 MiB e os limites representáveis do PRT. Esses limites protegem memória, disco e a estabilidade do computador.

As animações psicodélicas foram refinadas para reduzir repintura: a sombra contínua dos cards foi removida, filtros caros foram reduzidos, movimentos são pausados quando a aba fica em segundo plano e o hover não fica preso em dispositivos touch. O modo `prefers-reduced-motion` continua sendo respeitado.

## Validação

A suíte completa passou com 235 testes. Também foram validados `compileall`, a sintaxe JavaScript do painel e renderizações desktop/mobile. A validação física do PRT e do perfil ICC continua obrigatória antes de produção.
