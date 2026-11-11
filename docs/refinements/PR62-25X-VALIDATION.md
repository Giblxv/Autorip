# PR 62 — validação de 25 ciclos

- Resultado: **25/25 ciclos aprovados**.
- A suíte completa foi executada em cada ciclo.
- Rodada final: **1025 testes aprovados**, 28 warnings conhecidos.
- Checks remotos: Linux e Windows aprovados; 4 sucessos e 1 skip esperado.
- O diff do PR contém somente benchmark e documentação; nenhuma alteração de produção.

## Decisão técnica

A hipótese `scipy_direct` foi rejeitada por ser mais lenta e usar mais memória.
`np.hypot` float64 também foi mais lento. `np.hypot` float32 reduziu o pico de
memória e mostrou apenas 0,26% de ganho na micro-benchmark de 25 repetições,
mas introduziu erro máximo de 4,0e-11 e não foi validado como saída PRT idêntica
no pipeline completo. O ganho está abaixo do limiar para promover a alteração.

O PR permanece draft e não deve ser mesclado.
