# RGB opaco nativo

O caminho padrão mantém uma imagem RGB privada e mutável, aplica RGB→RGB via LittleCMS in-place e entrega um wrapper sem arquivo aberto. O cache limita entradas e bytes, separando transformações RGB e RGBA. Origem mapeada é copiada antes de alterar; chave de cor, paleta e alfa mantêm o fallback RGBA. Hooks personalizados de carregamento/conversão conservam o contrato anterior.

A prévia continua capturada antes do ICC. Reamostragem RGB evita a expansão completa para alfa premultiplicado; renderização RGB dispensa extração de canais e multiplicação por alfa opaco. Não altera geometria, orçamento de tiras, canais, morfologia nem formato PRT.

## Evidência

Protótipo `d975c05`; comparação explícita com `4080d82` (runtime da main `7095fe0`). Linux/Python 3.12/Pillow 13, CPUs 0–3. Exploração: 7 casos × 3 pares; confirmação independente: 8 × 5 pares; A/A: 4 × 5 pares. São **162 workers novos**, sem descarte de amostras. Cronômetro inclui RIP + captura + duas prévias JPEG/fsync, excluindo importação, inicialização e hashes. Não mede upload, fila completa ou impressora.

| Confirmação | Razão tempo antigo/novo | RSS antigo → novo (MiB) |
| --- | ---: | ---: |
| RGB ICC 90 MP | 1,195 | 739,8 → 576,4 |
| RGB sem ICC 90 MP | 1,779 | 739,5 → 576,3 |
| JPEG ICC 90 MP | 1,373 | 739,7 → 576,5 |
| RGB EXIF 90 MP | 1,257 | 739,7 → 739,6 |
| RGB / PRT ~238 MB | 1,177 | 818,5 → 743,9 |
| RGB / ICC de saída | 1,383 | 741,0 → 571,7 |
| RGBA controle | 1,130 | 740,1 → 740,2 |
| CMYK controle | 1,138 | 386,4 → 386,4 |

Os controles A/A deram razões 0,891 (RGB), 0,991 (RGBA), 1,124 (CMYK) e 1,137 (ICC de saída). Portanto as razões de tempo acima são descritivas, sem precisão suficiente para promessa global. A exploração do ICC de saída deu 0,879 antes de inverter na confirmação: esse resultado também é preservado. O aceite se baseia na redução de RSS nativo repetida (>15% nos casos RGB/JPEG sem rotação) e igualdade dos arquivos. Isso não altera retrospectivamente a rejeição da hipótese de retícula estreita.

A suíte completa do protótipo passou 1084 testes no Pillow 13; a seleção de compatibilidade passou 296 no Pillow 12.3; 60 testes específicos cobrem ownership, fechamento, leitura somente, ICC, EXIF, fallbacks, hooks e 32 configurações de PRT comparadas ao caminho RGBA. Os 30 PRTs da suíte de campanha e os limites numéricos da morfologia coincidiram.

[Relatórios brutos e decisão](../../benchmarks/campaign_runs/2026-11-11-opaque-rgb/). Os arquivos grandes não são versionados; `benchmark_reused_preview.py` gera os casos e `make_opaque_rgb_exif.py` acrescenta EXIF sem recodificar pixels.

A campanha anterior sobre `7095fe0` foi interrompida após 20 rejeições, sem aceite. O contador reinicia sobre RGB nativo; nenhuma sequência de bases distintas é somada. A primeira passagem sobre `4326a12`, com 25 rejeições, também permanece separada. A campanha final será registrada com seu motivo real de parada, 25 rejeições consecutivas ou 22h de São Paulo.
