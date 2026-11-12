# Fase final de RIP

Motivo real de parada: `deadline`. Rodadas concluídas: 6; aceites: 0; sequência final sem ganho: 6; alvo: 25. Convergência alcançada: False. Rodadas parciais e erros de infraestrutura não contam. Não se soma a sequência anterior da suíte v2 nem a da versão 0.8.22.

Suíte v3: 30 PRTs de correção e 12 cenários cronometrados, incluindo a folha opaca de 6000 pontos. A ampliação evita testes inertes de políticas ativadas apenas acima de 4096 pontos. As três rodadas v2 anteriores ficam separadas. Os pares de hashes históricos impedem repetir variantes já testadas no mesmo líder.

A auditoria independente verificou histórico, reinícios do contador, hashes, checkout e 30 PRTs idênticos. O snapshot final foi derivado da última candidata aceita ou da base; isso não altera a flag de conclusão original do relatório. Os TXT preservam o driver e propostas medidos. O pico é tracemalloc, sem todo o RSS nativo. Os resultados não provam ótimo global para toda imagem ou máquina.
