# Perfil por etapa e protótipos CPU/GPU

## Perfil inicial

O benchmark `benchmarks/profile_stages.py` mede cinco execuções de uma arte RGBA
larga (4096x3072), sem alterar o caminho de produção. No ambiente Linux atual,
o tempo mediano total foi **0,2805 s**. Os principais componentes observados
foram:

| Etapa | Mediana | Interpretação |
|---|---:|---|
| carregamento/conversão da fonte | 0,1281 s | leitura, decode e RGBA/ICC |
| morfologia do branco/EDT | 0,1515 s | maior etapa computacional isolada |
| preparação para resize | 0,0311 s | conversão do raster para reamostragem |
| conversão CMYK | 0,0175 s | conversão e limite de tinta |
| expansão de thresholds | 0,0052 s | tela periódica |
| empacotamento/gravação PRT | 0,0120 s | `pack2` e I/O |

Os tempos internos se sobrepõem ao tempo de renderização total; não devem ser
somados. O resultado prioriza a investigação de EDT/morfologia e decode/ICC,
não o empacotamento PRT.

## ProcessPool experimental

`autorip.experimental_processpool.process_files` é opt-in. Cada arte é processada
por um processo isolado com seu próprio `Rip`, Pillow e estado LittleCMS. O
executor usa `spawn`, recebe somente dados serializáveis e mantém a publicação
independente de cada PRT. O servidor padrão não o utiliza.

A implementação só poderá ser integrada ao fluxo principal após benchmark
comparativo de lote, validação de ordem/saída, limites de memória, 25 ciclos,
Linux/Windows e confirmação de que o custo de criar processos não supera o
ganho em lotes pequenos.

## GPU experimental

`autorip.experimental_gpu` tenta usar CuPy/CuPyX para EDT, dilatação e erosão.
CuPy, CUDA e Numba são opcionais. Sem GPU, o módulo falha de maneira explícita
e segura; nenhum import de GPU é obrigatório para o AutoRIP CPU.

O ambiente desta campanha não possui `nvidia-smi`, CuPy ou Numba. Portanto, o
benchmark GPU só pode registrar indisponibilidade aqui. Em uma máquina CUDA,
o benchmark deve comparar o resultado com `_distance` da CPU e exigir erro zero
ou tolerância documentada, além de incluir custo de transferência CPU/GPU.

Nenhuma dessas experiências está habilitada por padrão nem é candidata a merge
sem a bateria completa de integração e desempenho.
