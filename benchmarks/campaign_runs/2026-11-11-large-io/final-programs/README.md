# Campanha final após RGB nativo, cache de ruído e melhorias do painel

Terminou em 11/11/2026 20:12:54 de São Paulo: **25 hipóteses consecutivas sem novo ganho validado**, 25 rodadas concluídas, 0 aceites adicionais. Motivo: `consecutive-without-gain`. A otimização RGB foi validada separadamente antes desta sequência; as passagens anteriores não são somadas.

Suíte `large-io-v2`: 30 casos de correção, 11 cronometrados, 15 pares por bateria, CPUs 0–3. Cada hipótese aplicável é única por líder. Noops, duplicatas, erros de infraestrutura e rodadas parciais não contam. Sete hipóteses já avaliadas sobre o mesmo bundle de RIP antes das melhorias do painel ficam excluídas para evitar repetição. Duas exclusões permanentes são: identidade de objetos que o RIP não exercita e `hypot` que altera uma fronteira física. Uma hipótese nova compara duas ufuncs com o despacho de clip no buffer CMYK; as demais propostas ainda não haviam sido medidas neste bundle de RIP.

O verificador independente confirmou a contagem, a cadeia de hashes, o checkout e **30 PRTs idênticos**. A comparação final usa a base RGB nativa, portanto não representa o ganho em relação à versão anterior. Quando os dois lados têm código idêntico, qualquer razão de tempo é A/A e não uma otimização.

O pico desta campanha é tracemalloc, sem toda a memória nativa. A redução de RSS das imagens de 90 MP foi medida separadamente nos 162 workers documentados em `../../2026-11-11-opaque-rgb/`.

Para verificar os módulos arquivados, extraia `source-snapshots.zip` em uma pasta nova e execute `benchmarks/verify_rip_campaign.py --work-dir PASTA --icc PERFIL`. Use `--check-checkout` somente se o código corresponder ao líder final. `source-manifest.json` confere cada entrada; os TXT preservam o driver e propostas usados.

Este encerramento atende ao critério de parada solicitado. Não demonstra ótimo global para todo hardware, imagem, perfil ICC ou dispositivo móvel.
