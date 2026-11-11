# Evidência das melhorias de desempenho do painel

`decision.json` identifica a versão anterior, o hash do HTML atual, o aceite e o reinício do contador. `browser-baseline.json` e `browser-final.json` guardam as 36 provas, incluindo testemunhos negativos do HTML antigo. `jobs-*.json` preservam todas as 2200 medidas de atualização em 44 processos novos do Chromium. O cenário é sintético, com 100 cartões sem miniaturas, layout forçado e movimento reduzido; não mede aparelho móvel ou aplicativo completo.

O ZIP contém o HTML anterior e atual, os scripts do navegador, o benchmark e o harness. `source-manifest.json` confere seus hashes. `full-final-panel.log`, os relatórios de miniaturas/planejamento e `queue.log` registram a validação funcional.

[Escopo, números e reprodução](../../../docs/refinements/PANEL-PERFORMANCE.md).
