# Auditoria SIMD/Cython da morfologia e EDT

## Código auditado

`autorip/morph.py` já delega a transformação de distância para
`scipy.ndimage.distance_transform_edt`, um kernel compilado em C. Os trechos
restantes são operações NumPy vetorizadas (`arange`, multiplicação, `square`,
`add`, `sqrt`) e recortes. Não existe laço Python por pixel que uma extensão
Cython possa substituir diretamente.

Cython também não está instalado no ambiente de desenvolvimento atual. Criar
uma extensão Cython para repetir operações que já são ufuncs SIMD não teria
justificativa sem um ganho medido e aumentaria a superfície de build Windows.

## Variantes medidas

Fixture: máscara aleatória de `1400x2200`, sampling `(1/2400, 1/720)`, 25
repetições, saída comparada byte a byte/erro máximo.

| Variante | Mediana | Pico Python medido | Erro máximo |
|---|---:|---:|---:|
| implementação atual com `return_indices` + ufuncs | 0,10713 s | 70,5 MiB | 0 |
| `scipy_direct` com `return_distances=True` | 0,11053 s | 96,9 MiB | 0 |
| pós-processamento com `np.hypot` float64 | 0,10931 s | 94,0 MiB | 0 |
| pós-processamento com `np.hypot` float32 | 0,10685 s | 58,7 MiB | 4,0e-11 |

A variante direta do SciPy foi cerca de 3,2% mais lenta e consumiu mais
memória. `np.hypot` float64 foi 2,0% mais lenta. Float32 ficou 0,26% mais
rápida e reduziu o pico, mas introduziu diferença numérica; o efeito é menor
que a variação observada entre rodadas e ainda não foi confirmado no PRT
completo.

## Decisão

Este PR é deliberadamente **draft** e contém apenas o benchmark reproduzível.
Nenhuma substituição de produção foi feita. As hipóteses SIMD foram rejeitadas
por ausência de ganho de tempo. O caminho atual permanece melhor candidato para
compatibilidade, memória e determinismo.

Uma futura extensão C/Cython só deve ser tentada com um kernel próprio que
elimine a alocação de índices ou implemente uma etapa que o SciPy não cobre;
caso contrário, ela duplicará código já otimizado em C e complicará o build
Windows sem benefício confirmado.
