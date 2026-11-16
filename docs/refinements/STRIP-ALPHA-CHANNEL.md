# Ler somente o alfa das faixas RGBA

Base: AutoRIP 0.8.41, commit `130dd40dd05e1c7fa07c72821f654d4ce624b84e`.
Após a extração RGB nativa, o renderizador ainda convertia a faixa RGBA
inteira para NumPy somente para usar `arr[..., 3]`. A rotina `_strip_alpha`
extrai A com Pillow e cria uma matriz uint8 desse único canal. O buffer
NumPy retido passa de quatro para um byte por pixel da faixa.

O raster Pillow de A existe temporariamente durante a extração e é fechado
antes de retornar. A matriz resultante mantém seus próprios bytes, continua
válida após fechar a origem e é contígua/somente leitura. A normalização
`astype(float32) / 255.0` e seu arredondamento permanecem iguais; não foram
substituídos por aproximação, recíproco ou mudança de precisão. O caminho
RGB opaco não passa pela nova rotina.

Para uma faixa de 4000 × 512 pixels, são 6.144.000 bytes a menos no buffer
NumPy retido. Isso não representa redução de 75% da RAM do RIP: a origem,
os canais RGB/CMYK, os planos e a morfologia também consomem memória. A
redução do buffer atua na etapa de cor; quando a morfologia determina o
pico global, o benefício pode ser menor ou não aparecer em RSS.

Carregamento, ICC, premultiplicação/redimensionamento, espelhamento,
retícula, branco, halos, workers, etiquetas e formato PRT mantêm suas regras
anteriores. `prt.py` e `morph.py` são idênticos à base.

## Verificação

**1.877 testes locais aprovados**, incluindo 32 novos: todos os valores
de alfa, faixas vazias/opacas/parciais, formas pequenas e largas, origem
preservada e matriz válida após fechar a imagem Pillow. Dezesseis RIPs
completos comparam os bytes e metadados do caminho antigo e novo em
PNG/TIFF, com ICC opcional, uma/quatro threads, espelhamento, branco,
limites de tinta, etiquetas, margens e canais remapeados.

Mais 30 artes RGB/RGBA distintas em PNG/TIFF produziram bytes e metadados
idênticos à 0.8.41. Os PRTs de todos os ensaios abaixo também têm SHA e
metadados iguais entre as versões comparadas.

## Método das medições

Linux/Python 3.12.14, NumPy 2.5.4, Pillow 13, quatro CPUs pela quota e cinco
visíveis ao sistema. Os ensaios foram sequenciais, sem pytest concorrente.
Duas rodadas de nove casos, 11 pares AB/BA por caso, aquecimento e controle
A/A totalizam 198 pares cronometrados, além de 72 saídas em processos
separados para medir pico RSS. O perfil ICC já pertence ao repositório;
seu hash e os hashes do código estão nos relatórios.

O tempo inclui abrir/preparar a imagem, renderizar, gravar, fsync e publicar
via `Rip.process`. Construção do motor, fila, upload, prévia e conferência
SHA ficam fora. As tabelas mostram medianas separadas por versão; os
intervalos bootstrap de 95% reamostram medianas das razões pareadas, que
são outro estimador. Os benchmarks verificam SHA e metadados iguais.

## RIP com motor aquecido

| Caso | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| `rgba_scaled` | 142.81 → 140.52 ms | 131.62 → 136.76 ms |
| `rgba_scaled_white` | 537.73 → 571.43 ms | 491.39 → 483.99 ms |
| `rgba_wide` | 301.35 → 289.14 ms | 280.74 → 275.75 ms |
| `rgba_wide_white` | 894.80 → 899.23 ms | 1060.16 → 1018.98 ms |
| `rgba_identity` | 21.36 → 20.55 ms | 20.84 → 20.43 ms |
| `rgba_large_source` | 1164.44 → 1147.18 ms | 1133.30 → 1201.25 ms |
| `small_rgb_control` | 18.01 → 17.91 ms | 18.21 → 19.02 ms |
| `large_rgb_control` | 94.91 → 95.64 ms | 84.42 → 97.10 ms |
| `rgba_icc_white` | 616.77 → 585.24 ms | 612.44 → 591.04 ms |

O RGBA 1:1 sem branco levou **2,0–3,8% menos tempo**; os intervalos
pareados ficaram acima de 1 nos dois ensaios (1,035–1,127 e 1,014–1,040).
Não há aceleração confirmada para todos os casos. No redimensionado com
branco, o primeiro ensaio ficou 6,3% mais lento, com intervalo abaixo de 1
(0,889–0,994); o segundo ficou 1,5% mais rápido, com intervalo inconclusivo
(0,959–1,224). Esse resultado desfavorável não foi omitido.

O controle RGB grande, que não usa a nova rotina, ficou 15% mais lento
na segunda rodada, com intervalo 0,860–0,998. Isso revela variação também
fora do caminho alterado. Os controles A/A incluem 1 nos dois ensaios
(0,943–1,052 e 0,919–1,064). Não se atribuem oscilações RGB à otimização.

### Pico de RAM residente

Medianas de duas saídas por versão/caso/ensaio, em MiB:

| Caso | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| `rgba_scaled` | 185.2 → 181.4 | 181.0 → 174.3 |
| `rgba_scaled_white` | 219.4 → 201.4 | 224.2 → 204.3 |
| `rgba_wide` | 318.8 → 300.2 | 305.6 → 288.1 |
| `rgba_wide_white` | 344.2 → 318.2 | 331.1 → 318.7 |
| `rgba_identity` | 74.3 → 72.9 | 73.2 → 73.0 |
| `rgba_large_source` | 295.9 → 274.0 | 290.9 → 275.7 |
| `small_rgb_control` | 59.1 → 59.1 | 59.1 → 59.2 |
| `large_rgb_control` | 117.7 → 113.2 | 115.0 → 113.5 |
| `rgba_icc_white` | 224.3 → 213.1 | 223.1 → 207.5 |

As duas rodadas reduziram o pico em aproximadamente 8–9% no RGBA
redimensionado com branco, 6% no largo sem branco, 4–8% no largo com
branco e 5–7% na origem RGBA de 12,6 MP. São medições dos casos sintéticos,
sem garantia de igual redução em cada arquivo ou computador.

## Processos novos

Mais 132 RIPs: quatro casos, 11 grupos aleatórios de base/nova/controle
base, cada execução em um processo novo, sem tracemalloc. Os contadores
confirmam a nova rotina apenas nas versões RGBA candidatas. O tempo de
CPU é medido dentro de `Rip.process`, antes de conferir o hash.

| Caso | Tempo: base / nova / controle | RSS: base / nova / controle |
| --- | ---: | ---: |
| `rgba_scaled_white` | 558.41 / 588.61 / 538.51 ms | 220.2 / 204.3 / 217.2 MiB |
| `rgba_wide` | 374.32 / 356.64 / 389.67 ms | 301.3 / 291.3 / 309.4 MiB |
| `rgba_identity` | 36.71 / 39.48 / 37.49 ms | 74.1 / 72.8 / 74.0 MiB |
| `large_rgb_control` | 145.62 / 136.44 / 141.48 ms | 113.2 / 113.4 / 113.2 MiB |

O RGBA redimensionado com branco apresentou 6–7% menos pico RSS contra
as duas referências; o largo sem branco, 3–6%. Não há ganho de tempo
confirmado contra as duas referências nos quatro casos: alguns intervalos
individuais indicam melhora, mas isso não se repete contra ambos os
controles. No 1:1 novo, por exemplo, a mediana ficou mais lenta, com
intervalos inconclusivos. Os ganhos de tempo anteriores se restringem
aos ensaios com motor aquecido. CPU, RSS, contadores, amostras e intervalos
completos estão no relatório.

## Etapa isolada

Extração do alfa, teste de presença e normalização float32, como no
renderizador; 21 grupos aleatórios de base/nova/controle e uma rodada
de aquecimento. O canal Pillow temporário é fechado antes de normalizar.

| Faixa | Base → nova | Buffer NumPy retido evitado |
| --- | ---: | ---: |
| 32x32 | 9.65 → 11.94 µs | 3,072 bytes |
| 1440x512 | 2679.73 → 982.60 µs | 2,211,840 bytes |
| 4000x512 | 5401.91 → 2441.07 µs | 6,144,000 bytes |

As duas faixas grandes levaram cerca de 2,2–2,7 vezes menos tempo nessa
etapa; isso não é a aceleração do RIP completo. A faixa 32 × 32 ficou
cerca de 2,3 µs mais lenta pelo custo fixo de extrair um canal. Portanto,
a extração não é mais rápida em todos os tamanhos. Tracemalloc mede os
buffers Python/NumPy, mas não todos os rasters/alocadores nativos Pillow.
Não se transforma sua redução em porcentagem de RAM global.

## Reprodução

```bash
python -m pytest -q
python benchmarks/verify_threshold_tiles.py --baseline-ref v0.8.41 --output /tmp/equivalence-30.json
python benchmarks/benchmark_cmyk_direct.py --baseline-ref v0.8.41 --pairs 11 --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc' --output /tmp/strip-alpha.json
python benchmarks/benchmark_strip_alpha.py --baseline-ref v0.8.41 --pairs 21 --output /tmp/strip-alpha-stage.json
python benchmarks/benchmark_strip_alpha_fresh.py --baseline-ref v0.8.41 --pairs 11 --output /tmp/strip-alpha-fresh.json
```

Dados completos: [ensaio](strip-alpha-benchmark.json),
[confirmação](strip-alpha-confirmation.json), [etapa](strip-alpha-stage.json),
[processos novos](strip-alpha-fresh.json) e
[30 artes distintas](strip-alpha-equivalence-30.json). O identificador
nos dois primeiros relatórios é o objeto da tag anotada v0.8.41, que aponta
para o commit base acima. Os hashes comprovam a mesma base e implementação
candidata nos quatro ensaios.

Não houve medição no computador do usuário nem prova física de impressão.
O APK 0.2.2 e o agente 0.2.1 mantêm suas versões nativas; uploads móveis
usam o motor atualizado no servidor.

## Controle adicional de artes pequenas e estreitas

Sete casos, 11 pares AB/BA cada, aquecimento, controle A/A e 28 saídas
RSS adicionais. Isso acrescenta 77 pares e leva o total a **275 pares
cronometrados e 100 saídas RSS**, além dos 132 RIPs em processos novos.
Todos os PRTs e metadados coincidem. O código medido é o mesmo.

| Caso | Base → nova | Intervalo 95% da razão pareada |
| --- | ---: | ---: |
| `rgba_one_strip` | 2.55 → 2.26 ms | 0.947–1.218 |
| `rgba_serial` | 33.82 → 33.08 ms | 0.970–1.077 |
| `rgba_tall` | 129.27 → 128.38 ms | 0.947–1.052 |
| `rgba_tall_white` | 301.42 → 300.13 ms | 0.931–1.028 |
| `rgb_tall` | 91.23 → 93.21 ms | 0.921–1.005 |
| `scaled_rgba_control` | 125.45 → 122.91 ms | 0.977–1.029 |
| `rgba_tall_output_icc` | 515.73 → 513.94 ms | 0.971–1.062 |

Essa rodada verifica pequena arte de 129 × 137 pixels, processamento
serial, origem estreita/alta, branco e ICC. Ela não substitui as duas
rodadas principais nem prova aceleração universal.
[Dados completos](strip-alpha-identity-controls.json).

Todos os intervalos desse controle adicional incluem 1; ele não encontrou
uma diferença conclusiva de tempo entre as versões nos sete casos.
