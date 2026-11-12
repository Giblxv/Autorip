# Validação de publicação

A busca de desempenho terminou no prazo registrado em `rip-final/`. Esta etapa posterior corrige apenas a instrumentação dos testes e os metadados da publicação; não retoma a pesquisa de desempenho.

O build da tag 0.8.23 ([execução 43132440702](https://github.com/Giblxv/Autorip/actions/runs/43132440702)) falhou antes de empacotar: o spy global de `outbox_load` contou uma leitura de um aplicativo iniciado em outro teste, em outra pasta. A lista de chamadas no erro identifica as duas pastas distintas. Não houve release pública 0.8.23. A tag é preservada.

Os dois testes HTTP agora observam somente a pasta da instância avaliada e encaminham todas as leituras ao loader original. Cada cenário injeta também uma leitura de outro aplicativo e verifica seu resultado, reproduzindo a interferência de forma determinística. As verificações de uma única decodificação, invalidação, conteúdo inválido e privacidade continuam ativas. Os 18 testes focados passaram; a matriz e o empacotamento completos são exigidos novamente na revisão 0.8.24. O código de produção do contador e do servidor não mudou nesta correção.
