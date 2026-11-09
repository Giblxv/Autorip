# Ripagem: campanha ampliada após integração da main

Continuação posterior: [menos espera na hot-folder com estabilidade em lote](BATCH-FLOW.md).
As 15 rodadas e medições abaixo permanecem como registro desta campanha do motor.

Base: `3606308`, integração da main v0.8.14 com o motor paralelo do PR #51.
Foram concluídas **15 rodadas adicionais consecutivas sem melhoria aceitável**.
Nenhuma hipótese alterou o motor de produção nesta campanha. O hash conjunto de
`engine.py`, `prt.py` e `morph.py` é idêntico no início e no final; os resultados
da comparação final são uma medição de controle do mesmo código, não um ganho
ou uma regressão atribuível a alterações.

A [campanha anterior](RIP-CAMPAIGN.md) continua como evidência histórica das
26 rodadas e dos ganhos incorporados naquele momento. São **41 rodadas nas
duas campanhas**, com escopos e bases diferentes; os ganhos anteriores não
foram medidos novamente contra a main atual.

## Escopo ampliado

A nova bateria mede seis cenários, em 720 × 2400 dpi:

| Cenário | Característica adicional |
| --- | --- |
| alpha | Transparência gradual, referência compacta |
| large_source | Entrada RGBA de 2400 × 2000 pixels (4,8 milhões) |
| wide_opaque | Saída de 6000 colunas, aproximadamente 21,17 cm de largura |
| wide_alpha | Saída de 3000 colunas com transparência gradual |
| icc_two_cpu | Perfil CMYK real, limite do motor de duas threads |
| icc_single_cpu | Perfil real, branco desligado, limite do motor de uma thread |

Os limites de uma/duas CPUs usam `os.cpu_count` simulado para controlar a escolha
de trabalhadores. Não representam máquinas físicas independentes nem alteram
a afinidade do processo. O ambiente Linux tem quota de quatro CPUs e informa
cinco CPUs disponíveis. Versões e restrições constam no registro de ambiente.

Além das medições, a comparação completa de **15 PRTs** cobre EXIF, TIFF, DPI
anisotrópico, canais remapeados, dois planos brancos, largura mínima e uma arte
larga com outra resolução vertical. Retícula nos limiares, empacotamento com
padding/strides e morfologia física também são comparados.

## Critério e resultados

São cinco repetições pareadas por cenário, ordem alternada e aquecimento.
Uma hipótese elegível precisa de confirmação independente antes do aceite.
A regra permanece: ganho geométrico >1,5%, limite inferior do bootstrap
pareado de 95% >1,005× e nenhum cenário mais de 6% lento; ou redução do maior
pico rastreado ≥8%, com média de tempo ≥0,99× e o mesmo limite por cenário.
Não basta que a média seja maior que 1. Erros de infraestrutura interrompem
a campanha e não contam como rodada. Saída diferente impede o aceite.

| Rodada | Hipótese | Resultado |
| --- | --- | --- |
| 1 | Erosão analítica de máscara preenchida | Ganho não confirmado |
| 2 | Branco opaco convertido diretamente para níveis 0/3 | Ganho não confirmado |
| 3 | Normalização CMYK no próprio buffer | Ganho não confirmado |
| 4 | Eliminar cópia da densidade float32 | Ganho não confirmado |
| 5 | Aplicar máscara de densidade no próprio buffer | Ganho não confirmado |
| 6 | Evitar multiplicação/alocação de alfa opaco | Regressão em cenário largo |
| 7 | Evitar cópia EXIF sem orientação | Ganho não confirmado |
| 8 | Tela de retícula float32 | Ganho não confirmado |
| 9 | Três trabalhadores em artes largas | Regressão no cenário largo opaco |
| 10 | Dois trabalhadores em artes largas | Regressão de desempenho |
| 11 | Estimativa de 80 bytes/pixel para aumentar tiras | PRT com transparência diferente |
| 12 | Estimativa de 64 bytes/pixel para aumentar tiras | PRT com transparência diferente |
| 13 | EDT transposta | Ganho não confirmado |
| 14 | Duas ufuncs no lugar de clip | Ganho não confirmado |
| 15 | Paralelismo a partir de 500 mil pixels | Ganho não confirmado |

As regressões observadas são motivos para recusar hipóteses nesta bateria;
não demonstram que ocorrerão em todo hardware. As tentativas de alterar o
orçamento por pixel mudaram o plano de tiras e falharam na igualdade de saída.
Foram descartadas antes das medições de desempenho.

O maior pico rastreado na comparação final do motor preservado foi **215,12 MiB**
nos cenários mais largos. A concorrência e o agendamento alteram esse pico mesmo
com código idêntico. Tracemalloc não mede todo o RSS/PIL/ICC nativo; o orçamento
de 512 MiB estima os buffers das tiras e não limita a RAM total do processo.
O paralelismo incorporado anteriormente continua trocando memória por vazão.

## Integração e verificação

A main trouxe pausa/cancelamento de trabalhos e validação de DPI de origem.
A integração preserva esses controles tanto no caminho sequencial como no
paralelo: antes de submeter/consumir tiras e após atualizar o progresso.
Os testes cobrem pausa e cancelamento depois de uma tira e na última atualização,
verificando que nenhum PRT parcial é publicado e que o temporário é removido.

A validação automática no Windows encontrou também uma disputa entre a fila
e a recuperação da hot-folder: os caminhos do histórico estavam normalizados
para maiúsculas/minúsculas, mas as chaves da fila não. O observador podia tratar
um trabalho ativo como abandonado. As chaves de entrada/liberação agora usam
o mesmo caminho canônico e `normcase`, e a recuperação consulta a fila viva
antes de ler o journal, mesmo se o snapshot anterior estiver desatualizado.
Um teste sem threads força o caso com caminhos equivalentes e, no Windows,
casing diferente, verificando deduplicação, bloqueio da recuperação e liberação.
Essa correção não altera os três módulos do motor medidos na campanha.

Validação local após a integração e correção da fila: **273 testes aprovados em 41,28 s**,
auditoria dos 15 PRTs e smoke do launcher v0.8.14 com login, upload, saída
720 × 2400 dpi e encerramento. O build Windows também executa o smoke contra
o executável empacotado, conforme o workflow existente.

- [Dados integrais das 15 rodadas](../../benchmarks/campaign_runs/2026-11-09-wide/report.json).
- [Auditoria e SHA-256 dos 15 PRTs](../../benchmarks/campaign_runs/2026-11-09-wide/verification.json).
- [Ambiente e identidade dos módulos](../../benchmarks/campaign_runs/2026-11-09-wide/environment.json).
- [Hipóteses reproduzíveis](../../benchmarks/rip_wide_candidates.py).

```bash
python benchmarks/rip_campaign.py --suite extended --baseline-ref 3606308 --work-dir /tmp/autorip-wide --icc /caminho/perfil-cmyk.icc --repeats 5
python benchmarks/verify_rip_campaign.py --work-dir /tmp/autorip-wide --icc /caminho/perfil-cmyk.icc
python -m pytest -q
```

`--apply` grava somente módulos aprovados. `--resume` retoma o líder persistido;
`--check-checkout` na auditoria exige que o checkout coincida com esse líder.
O hash do ICC usado localmente consta na auditoria. Não foi adicionado perfil
novo, dependência ou mudança de resolução/modelo físico do branco.

O critério de parada foi atendido nos cenários medidos. Isso não prova um ótimo
global para toda arte, máquina, disco ou impressora. Não houve validação física
em impressora/PrintExp/Hoson. Esta continuação atualiza o PR #51, sem publicação
automática de uma nova release.
