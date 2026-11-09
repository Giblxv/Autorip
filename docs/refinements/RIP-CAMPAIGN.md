# Campanha de ripagem: 15 rodadas consecutivas sem ganho aceito

Continuação: [campanha ampliada após integração da main](RIP-WIDE-CAMPAIGN.md).
As medições abaixo se referem à base e ao código desta campanha original.

Base: `eaa2f7c`, refinamento inicial do PR #51, posterior à v0.8.13.
Esta campanha altera somente a execução do motor; não reduz resolução, canais,
ICC, transparência ou o modelo físico do branco. A fila otimizada do PR inicial permanece.

## Critério e encerramento

Foram concluídas **26 rodadas**, com **7 aceites experimentais**. As rodadas
**12 a 26** foram as **15 consecutivas sem novo ganho aceito**. Isso encerrou a busca.
Três aceites foram incrementos do limite de paralelismo (2 → 3 → 4);
o código final combina cinco mudanças funcionais, não sete algoritmos independentes.

Uma rodada avalia uma hipótese aplicável: compila os módulos candidatos, compara
retícula nos limiares, empacotamento e morfologia, verifica SHA-256 de dez PRTs
contra a base imutável e mede cinco cenários em sete execuções pareadas, alternando
a ordem. Há aquecimento e uma segunda bateria independente antes de aceitar um ganho.
Hipóteses não aplicáveis são ignoradas; erros de infraestrutura não contam como rodada.

A regra de velocidade exige ganho geométrico superior a 1,5%, limite inferior do
bootstrap pareado de 95% acima de 1,005×, e nenhum cenário mais de 6% lento.
Também se aceita redução rastreada de memória de pelo menos 8%, com média de tempo
sem regressão superior a 1%. O teto de rastreamento foi 512 MiB. Esses limites
evitam aceitar ruído; não são uma prova de ótimo global em todo hardware/imagem.

## Mudanças incorporadas

- Planos sem tinta compartilham um buffer vazio. As etiquetas fazem cópia antes
  de escrever em K, para não contaminar os demais canais.
- O PRT reaproveita o empacotamento de views com mesmo endereço, strides e dtype.
  O cache é local ao bloco e não reaproveita dados de outro trabalho.
- Tiras totalmente transparentes pulam conversão CMYK, retícula e branco,
  preservando a emissão de etiquetas.
- A EDT usa a API pública de índices da SciPy e calcula distâncias em buffers 2-D,
  sem construir a grade completa `np.indices`. A comparação dos valores com a
  EDT pública é exata nos testes, inclusive em grades anisotrópicas.
- Até quatro tiras são renderizadas em paralelo, com escrita ordenada. O número
  é limitado pelas CPUs informadas; imagens pequenas ficam sequenciais.
  O orçamento de 512 MiB estimados é compartilhado entre as tiras. Quando uma
  tira por trabalhador não cabe, o motor recua para uma thread. Falhas impedem
  a publicação do PRT e removem o temporário após aguardar os trabalhadores.
- O transformador LittleCMS compartilhado usa `NOCACHE`, evitando o cache mutável
  de pixel durante o uso concorrente. Intenção de renderização, compensação de
  ponto preto, perfil e valores de saída são preservados.

## Aceites e sequência final

| Rodada | Hipótese aceita | Critério |
| --- | --- | --- |
| 2 | Compartilhar plano vazio e alocar somente canais usados | confirmed-memory |
| 3 | Empacotar uma vez os planos com memória idêntica | confirmed-speed |
| 4 | Não converter nem reticular tiras totalmente transparentes | confirmed-speed |
| 8 | Construir distâncias em buffers 2-D a partir de índices públicos | confirmed-speed |
| 9 | Renderização ordenada em até 2 threads com orçamento global | confirmed-speed |
| 10 | Renderização ordenada em até 3 threads com orçamento global | confirmed-speed |
| 11 | Renderização ordenada em até 4 threads com orçamento global | confirmed-speed |

| Rodada sem aceite | Hipótese | Fator medido* |
| --- | --- | ---: |
| 12 | Expandir tela com duas operações take | 1.027× |
| 13 | Expandir linhas com tile e recortar colunas | 1.053× |
| 14 | Repetir matriz periódica em dois eixos | 0.964× |
| 15 | Expandir tela por broadcast 4-D e reshape | 1.001× |
| 16 | Empacotamento hierárquico em pares de pixels | 1.003× |
| 17 | Empacotar sem preencher a imagem até a largura alinhada | 1.000× |
| 18 | Produto escalar uint8 para agrupar quatro pixels | 0.978× |
| 19 | Soma ponderada uint8 para empacotamento | 0.821× |
| 20 | Empacotamento vetorizado com packbits | 0.969× |
| 21 | Leitura de grupos de quatro pixels como palavras uint32 | 1.034× |
| 22 | Escrever gotas grandes por máscara sobre saída uint8 | 1.001× |
| 23 | Combinar níveis por operações bit a bit | 1.028× |
| 24 | Atalho para canal inteiramente saturado | 1.006× |
| 25 | Copiar canal CMYK para acesso contíguo antes da retícula | 1.012× |
| 26 | Normalizar CMYK com tabela exata de 256 entradas | 0.951× |

*Última bateria disponível da rodada. Um fator acima de 1 sozinho não basta:
a confirmação, o intervalo pareado e os demais cenários também precisam passar.

## Resultado combinado

Linux, Python 3.12.14, NumPy 2.5.4, quota de quatro CPUs no ambiente
(o sistema informa cinco CPUs). Medianas de sete execuções; ICC real de
avaliação usado localmente. Não foi adicionado nenhum perfil novo ao repositório.

| Cenário do motor | Início da campanha | Final | Fator |
| --- | ---: | ---: | ---: |
| alpha | 375.71 ms | 135.79 ms | 2.77× |
| icc | 364.09 ms | 152.07 ms | 2.39× |
| no_white | 113.70 ms | 50.27 ms | 2.26× |
| sparse | 243.74 ms | 100.02 ms | 2.44× |
| large_source | 488.72 ms | 178.89 ms | 2.73× |

Ganho geométrico combinado: **2.51×**.
A medição inclui abertura da imagem, RIP, gravação, flush/fsync e publicação
do PRT, mas não inclui espera de hot-folder, notificações ou impressora.

O paralelismo troca memória por vazão: o maior pico rastreado passou de
**25.81 MiB** para **68.08 MiB**.
Tracemalloc não representa todo o RSS nem o decoder/PIL/ICC nativo. O orçamento
do motor limita os buffers estimados das tiras; imagem de entrada, perfis e
outros componentes também consomem RAM. O ganho varia com CPUs, arte, ICC e disco.

## Evidências e reprodução

- [Registro integral das 26 rodadas](../../benchmarks/campaign_runs/2026-11-09/report.json).
- [Auditoria da contagem e SHA-256 dos dez PRTs](../../benchmarks/campaign_runs/2026-11-09/verification.json).
- [Hipóteses reproduzíveis](../../benchmarks/rip_candidates.py).
- [Executor da campanha](../../benchmarks/rip_campaign.py).

```bash
python benchmarks/rip_campaign.py --baseline-ref eaa2f7c --work-dir /tmp/autorip-campaign --icc /caminho/perfil-cmyk.icc
# --apply é opcional: grava no checkout somente os módulos aprovados.
# --resume retoma o líder persistido quando executado com --apply.
# --check-checkout no verificador também confere os módulos do checkout.
python benchmarks/verify_rip_campaign.py --work-dir /tmp/autorip-campaign --icc /caminho/perfil-cmyk.icc
python -m pytest -q
```

A comparação do ICC exige uma cópia local do mesmo perfil; seu hash consta
na auditoria. Nenhum download ou serviço externo participa da campanha.
Não houve validação física em impressora/PrintExp/Hoson.

O smoke do executável usa agora 720 × 2400 dpi e saída de 2,54 cm, exercitando
a nova execução paralela no runner Windows, além de login/upload/PRT/encerramento.
Esta proposta não publica release nem incorpora automaticamente código na main.
