# Menos buffers no RIP e menos leituras na fila

Base: `v0.8.13`, commit `fbeb55fa715e369d7cc06f086bea12ef0e1efecc`.

## Resultado

A retícula preserva a mesma aritmética, fase de ruído e níveis 0/1/3. A seleção
usa uint8 em vez de materializar duas matrizes int64. A tela de limiares é
reutilizada entre os quatro canais CMYK e descartada antes de preparar o branco.
Os buffers de cor já utilizados são liberados antes da EDT, que é a etapa com
maior uso de memória no perfil medido. Limites de tinta e aplicação do alfa usam
operações no próprio buffer float32. A escrita PRT passa um memoryview contíguo
ao gravador, evitando a cópia de cada bloco para bytes.

O fechamento de uma máscara inteiramente preenchida retorna sem executar duas
transformadas de distância: esse fechamento preserva a máscara. A erosão continua
tratando o exterior como fundo. Máscaras parciais mantêm o caminho EDT anterior.

A consulta da fila foi extraída para `autorip.prints.PrintCatalog`. Um cache em
memória, limitado a 512 registros e protegido contra consultas concorrentes,
reaproveita cabeçalhos e dimensões. A chave usa identidade, tamanho e timestamps
em nanossegundos do PRT e do sidecar. Alterar, substituir, remover ou criar um
sidecar invalida o registro. Arquivos removidos deixam o cache na próxima consulta;
consultar outra pasta também substitui o conjunto anterior.

As ações de mover/excluir continuam validando o arquivo real, sem consultar o
cache de apresentação. Arquivos inválidos, diretórios e symlinks não entram na
fila. Margens alteradas recalculam as dimensões de fallback a cada consulta.

Duas correções acompanham o cache:

- O FIFO usa mtime em nanossegundos, com desempate estável por nome. Antes, truncar
  para segundos deixava arquivos chegados no mesmo segundo dependentes da ordem
  de listagem do sistema de arquivos.
- A URL da miniatura inclui uma versão derivada de sua identidade no disco.
  Substituir uma imagem mantendo o nome provoca um novo download autenticado,
  em vez de reutilizar por até 60 segundos o blob anterior do navegador.

## Medições

Linux, Python 3.12.14 e NumPy 2.5.4. Comparação com arquivos de código da própria
v0.8.13, aquecimento e mediana de sete execuções alternando a ordem das versões.
Valores sintéticos; hardware, arte, sistema de arquivos e ICC mudam os resultados.

| Operação | v0.8.13 | Refinamento |
| --- | ---: | ---: |
| Retícula 512 × 1700 | 10,99 ms | 7,91 ms |
| Branco parcial 640 × 1700 | 143,32 ms | 136,61 ms |
| Branco inteiramente opaco 640 × 1700 | 153,40 ms | 51,78 ms |
| RIP 5 × 3,75 cm, 720 × 2400 dpi | 1,553 s | 1,458 s |
| Pico rastreado da retícula | 21,58 MiB | 14,11 MiB |
| Pico rastreado de uma tira de renderização | 56,72 MiB | 40,12 MiB |

O pico acima mede alocações rastreadas por tracemalloc, incluindo buffers NumPy;
não representa todo o RSS do processo, a imagem de entrada ou qualquer trabalho
maior que o cenário medido. A redução do RIP foi de 6,1% e a do pico rastreado de
renderização, de 29,3%. Os arquivos completos comparados com e sem branco foram
idênticos byte a byte.

Em onze consultas aquecidas a uma fila de 200 PRTs, a mediana caiu de 4,98 ms para
2,03 ms (2,46×). As leituras de cabeçalho por consulta caíram de 200 para zero.
A consulta ainda faz stat dos arquivos: o catálogo precisa detectar mudanças.
O limite de 512 entradas evita crescimento ilimitado; filas maiores podem reler
os arquivos que não couberem no cache.

Reprodução:

```bash
git show v0.8.13:autorip/engine.py > /tmp/autorip-engine.py
git show v0.8.13:autorip/prt.py > /tmp/autorip-prt.py
git show v0.8.13:autorip/morph.py > /tmp/autorip-morph.py
git show v0.8.13:autorip/server.py > /tmp/autorip-server.py
python benchmarks/benchmark_rip.py --baseline /tmp/autorip-engine.py --baseline-prt /tmp/autorip-prt.py --baseline-morph /tmp/autorip-morph.py --repeat 7
python benchmarks/benchmark_print_catalog.py --baseline /tmp/autorip-server.py --count 200 --repeat 11
```

Resultados: [RIP e memória](../../benchmarks/render-results-v0.8.13-linux.json),
[catálogo](../../benchmarks/catalog-results-linux.json).

## Verificações

`python -m pytest -q`: **242 testes aprovados em 36,13 s**, localmente.
Regressões adicionadas cobrem limiares e valores vizinhos float32, razões de gota,
fases de ruído, CMYK com limites de tinta, canais reordenados, dois planos de
branco, etiquetas, igualdade de bytes, PRT multibloco, invalidação e limite do
cache, consultas concorrentes, FIFO dentro do mesmo segundo e mudança de URL
quando o JPEG é substituído.

Chromium/Playwright: upload e PRT reais, sessão e miniaturas protegidas, formulário
mobile, interruptor por teclado, movimento reduzido, progresso 100%, conexão
perdida/recuperada e DOM estável em repouso. Um teste adicional substituiu o JPEG
sob o mesmo nome: a imagem exibida mudou para a nova cor e a URL foi renovada.
Sem erros JavaScript ou CSP nos percursos observados.

O formato PRT e a morfologia física permanecem os da v0.8.13. Não houve validação
física em impressora. Este refinamento não publica nova release nem migra
configurações; pode ser revertido sem apagar dados ou journals.
