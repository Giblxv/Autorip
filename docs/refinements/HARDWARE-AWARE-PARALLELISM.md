# Dimensionamento de workers conforme o hardware disponível

## Mudança

O motor já usa `ThreadPoolExecutor` para renderizar tiras e mantém um teto de
quatro workers, além de um orçamento global de 512 MiB. Antes desta mudança, a
quantidade de workers era limitada apenas por `os.cpu_count()`. Em Linux,
`os.cpu_count()` pode refletir CPUs instaladas enquanto o processo está preso a
uma afinidade menor por contêiner, serviço ou política do sistema.

`autorip.engine._available_cpu_count()` agora usa o menor valor entre
`os.cpu_count()` e `os.sched_getaffinity(0)` quando a API existe. Em plataformas
sem afinidade POSIX, mantém o fallback portátil para `os.cpu_count()`. O teto de
quatro workers, o orçamento de memória e a ordem de escrita não foram alterados.

A escolha segue a documentação do NumPy: os kernels SIMD são selecionados em
runtime conforme os recursos efetivamente detectados da CPU [1]. O código do
Autorip não duplica esse despacho SIMD. Também segue a documentação do SciPy:
muitas operações NumPy/SciPy liberam o GIL e podem ganhar com threads quando cada
worker possui seus próprios arrays, mas arrays mutáveis compartilhados exigem
cuidado [2]. O motor continua isolando as tiras e publicando os blocos na ordem.

A alteração não tenta mover o pipeline para GPU. O caminho atual depende de
Pillow, LittleCMS, NumPy, SciPy, meio-tom e empacotamento PRT. Pillow suporta TIFF
em formatos striped e tiled, mas isso não constitui sozinho um pipeline out-of-
core seguro para o RIP [3]. Uma futura mudança para tiles precisará de validação
por formato, ICC, alfa, EXIF e igualdade byte a byte dos PRTs.

## Validação

Baseline antes da alteração: **1021 testes aprovados em 65,45 s**.

Validação focada após a alteração: **57 testes aprovados em 3,81 s**, incluindo
paralelismo, engine, afinidade e fallback sem `sched_getaffinity`.

Benchmark pareado no mesmo processo, Python 3.12.3, NumPy 2.5.4, Linux:

- PRT com branco: bytes idênticos entre baseline e candidato.
- PRT sem branco: bytes idênticos entre baseline e candidato.
- Pico de memória do meio-tom: 14,11 MiB em ambos.
- Pico de memória do render: 31,14 MiB em ambos.
- Tempos: variação entre -1,8% e +0,5%, sem ganho estatisticamente atribuível
  neste host, porque a afinidade disponível já é de seis CPUs e o teto atual é
  quatro workers.

A execução completa, a matriz Windows/Linux e os 25 ciclos de integração e
performance continuam obrigatórios antes de promover o PR a `main`. Esta mudança
é uma proteção contra oversubscription em ambientes restritos; não é apresentada
como aceleração universal.

## Reprodução

```bash
python -m pytest -q
python -m pytest -q tests/test_parallel_rip.py tests/test_engine.py
python benchmarks/benchmark_rip.py \
  --baseline /tmp/autorip-engine-before-affinity.py \
  --repeat 5
```

## Referências

[1]: https://numpy.org/doc/2.2/reference/simd/index.html "NumPy CPU/SIMD optimizations"
[2]: https://docs.scipy.org/doc/scipy/tutorial/thread_safety.html "SciPy Thread Safety"
[3]: https://pillow.readthedocs.io/en/latest/handbook/image-file-formats.html "Pillow Image File Formats"
