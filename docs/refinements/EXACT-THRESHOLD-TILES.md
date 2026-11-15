# Limiares float32 exatos para RGBA e branco

Base: `fe37f28`, AutoRIP 0.8.36. O motor conserva a retícula original em
float64 e cria, sob demanda, uma cópia somente leitura em float32 para
construir os planos periódicos do meio-tom. O plano expandido usa quatro bytes
por elemento em vez de oito. Não há mudança na normalização CMYK, nos cálculos
de tinta/alfa/branco, na resolução ou na decisão das gotas.

## Por que não há perda de precisão

Os 65.536 valores nativos são uma permutação de `(k + 0,5) / 65536`, ou seja,
inteiros ímpares divididos por 131072. Esses valores precisam de no máximo
17 bits significativos, dentro dos 24 bits de precisão do float32. Cada
limiar é exatamente o mesmo número em ambos os tipos. Compará-lo com as
probabilidades já calculadas em float16/32/64 mantém a desigualdade estrita.
As operações que calculam as probabilidades não mudam de precisão ou ordem.

Ainda assim, o motor exige igualdade exata entre a cópia e o ruído antes de
usá-la. Ruído substituído, mutável, não representável ou métodos personalizados
mantêm o caminho anterior. Limiares explicitamente fornecidos ao meio-tom
continuam sendo usados diretamente. O ruído original e os ranks/tabelas do
atalho RGB opaco da 0.8.36 são preservados.

Uma única cópia de 256 KiB por instância Rip é criada quando a retícula precisa
ser repetida; chamadas dentro de um único período continuam usando a vista
float64 original, sem esse custo. A cópia não retém imagens. Não há mudança na
altura das tiras, halos, fases, número de workers, ICC, canais, etiquetas,
PRT, hash, journal ou publicação.

## Verificação

**1.608 testes locais aprovados**, incluindo 49 novos: fases nas bordas do
período; todos os limiares e volumes adjacentes em float16/32/64; três razões
de gota; cópia limitada e somente leitura; vista sem alocação no caso pequeno;
ruído/métodos personalizados; limiares externos; e 12 RIPs transparentes com
ICC opcional, branco, canais remapeados, margens, mirror, etiquetas e uma ou
quatro threads. Os testes anteriores do atalho RGB também passaram.

Uma conferência adicional usou **30 artes distintas PNG/TIFF, RGB/RGBA**,
variando sementes, dimensões, ICC, densidade, ratio, etiquetas e workers. Todos
os PRTs foram comparados byte a byte, com metadados iguais. As saídas têm 30
SHA-256 distintos. [Registro](threshold-equivalence-30.json).

## Medição

Dois ensaios independentes em Linux, Python 3.12.14, NumPy 2.5.4, Pillow 13,
com quatro CPUs disponíveis pela quota, sem testes concorrentes. Cada caso
usa sete pares AB/BA, aquecimento, SHA-256 e metadados exatos. Os módulos
`prt.py` e `morph.py` são idênticos à base. O cronômetro de `Rip.process`
inclui abrir/preparar a arte, renderização, escrita, fsync e publicação do PRT;
construção do motor, espera da fila, upload, prévias e conferência SHA ficam
fora. As imagens são sintéticas. O perfil ICC do repositório tem o hash
registrado nos relatórios.

| Caso | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| RGBA pequeno, um período | 2.39 → 2.55 ms | 2.46 → 2.53 ms |
| RGBA longo 1:1 | 155.94 → 150.44 ms | 154.74 → 143.83 ms |
| RGBA longo com branco | 345.97 → 332.39 ms | 345.00 → 322.79 ms |
| RGBA longo com ICC e branco | 501.70 → 484.91 ms | 558.70 → 510.59 ms |
| RGB pequeno | 24.12 → 22.92 ms | 23.36 → 21.74 ms |
| RGB redimensionado, controle | 120.72 → 119.25 ms | 114.76 → 120.51 ms |
| RGBA redimensionado com branco | 585.77 → 592.73 ms | 583.51 → 557.81 ms |
| RGB com ICC e branco | 425.12 → 430.83 ms | 369.05 → 365.91 ms |
| RGBA largo, 4000 colunas | 1153.57 → 1133.96 ms | 1226.74 → 1027.72 ms |

O caso RGBA longo com ICC e branco levou **3,3–8,6% menos tempo** nas
medianas; seus intervalos pareados de 95% ficaram acima de 1x nos dois ensaios.
Os casos longos sem ICC e o RGB pequeno também tiveram medianas menores, mas
alguns intervalos incluíram 1x. Não se afirma ganho consistente de tempo para
esses casos, nem para o RGBA largo: nele a mediana variou de 1,7% a 16,2% menos
tempo, com intervalos incluindo 1x. Os controles RGB/RGBA redimensionados e
RGB com ICC/branco alternaram de sinal. O RGBA de um período não usa a cópia
nova; os tempos de cerca de 2,5 ms oscilaram ligeiramente para cima.

| Pico RSS | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| RGBA pequeno, um período | 52.2 → 52.4 MiB | 52.3 → 52.5 MiB |
| RGBA longo 1:1 | 141.0 → 129.2 MiB | 140.1 → 129.1 MiB |
| RGBA longo com branco | 143.7 → 133.8 MiB | 147.1 → 135.4 MiB |
| RGBA longo com ICC e branco | 145.4 → 141.8 MiB | 146.0 → 141.8 MiB |
| RGB pequeno | 60.7 → 59.3 MiB | 60.7 → 59.4 MiB |
| RGB redimensionado, controle | 121.0 → 120.4 MiB | 120.6 → 121.2 MiB |
| RGBA redimensionado com branco | 256.4 → 260.6 MiB | 273.8 → 255.6 MiB |
| RGB com ICC e branco | 171.9 → 153.6 MiB | 172.4 → 156.7 MiB |
| RGBA largo, 4000 colunas | 359.1 → 348.9 MiB | 373.0 → 343.9 MiB |

A redução do pico total foi **7,8–8,4% no RGBA longo sem branco**,
**6,9–8,0% com branco** e **9,1–10,7% no RGB com ICC/branco**. O RSS é medido
em processos novos, duas amostras por versão/caso, incluindo imports, decoder
e leitura do PRT após o cronômetro. Não representa só os buffers de limiares
nem uma sessão Windows longa. O RGBA redimensionado oscilou para cima no
primeiro ensaio e para baixo na confirmação; não há redução universal de RAM.

Os controles A/A tiveram 1,008x e 0,991x, ambos com intervalos incluindo 1x.
Foram **126 pares medidos** com PRTs e metadados iguais, mais aquecimentos,
controles A/A e **72 saídas de workers RSS**. [Ensaio](threshold-tiles-benchmark.json)
e [confirmação](threshold-tiles-confirmation.json) contêm tempos individuais,
intervalos, hashes e metadados. Não houve medição no Xeon do usuário nem
validação física na impressora. Não há alteração de APK nesta versão;
o processamento das artes enviadas pelo celular usa este mesmo motor.

## Reprodução

```sh
python -m pytest -q
python benchmarks/verify_threshold_tiles.py --baseline-ref v0.8.36 --output /tmp/equivalence-30.json
python benchmarks/benchmark_threshold_tiles.py --baseline-ref v0.8.36 --pairs 7 --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc' --output /tmp/thresholds.json
python benchmarks/benchmark_threshold_tiles.py --baseline-ref v0.8.36 --pairs 7 --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc' --output /tmp/thresholds-confirmation.json
```
