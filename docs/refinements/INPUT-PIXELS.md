# Artes de entrada sem teto artificial de pixels

A v0.8.18 remove o limite de 80.000.000 pixels. O bloqueio estava repetido no
motor, nos uploads, no planejamento e nos anexos Trello; a remoção de fundo
opcional possuía outra cópia do mesmo número. A prévia também aplicava esse teto.
Todos esses caminhos agora aceitam a dimensão original da arte.

O Pillow impunha outro limite durante `Image.open`, inclusive antes da validação
do AutoRIP. `autorip.imaging` configura `Image.MAX_IMAGE_PIXELS = None` uma única
vez por processo. Os leitores de imagens compartilham esse módulo, inclusive
quando são importados separadamente. Não se alterna uma configuração global
por requisição/thread e não se silenciam outras categorias de avisos.

O tamanho que pode ser processado depende da memória e do disco disponíveis.
Continuam a validação do arquivo, as dimensões positivas, a reserva de disco,
o orçamento das tiras e os limites representáveis do PRT. A dimensão escolhida
para impressão continua determinando a resolução de saída, como nas versões anteriores.

## Validação

- **767 testes passaram** na suíte local, incluindo 12 novos casos para artes grandes.
- Um PNG válido de **400 MP**, gerado em streaming com 1 bit por pixel, confirma
  abertura e verificação em cinco processos independentes: motor, painel,
  planejamento, integrações e remoção de fundo. Cada processo usa avisos de
  decompression bomb como erros; o teste passa sem decodificar o raster.
- Upload, hot folder, planejamento e download Trello passam pela admissão sem
  materializar os pixels. Motor, miniatura e remoção de fundo chegam ao decoder;
  um sinal de teste interrompe nesse ponto para evitar alocar um RGBA de 400 MP no CI.
- Uma imagem **RGBA de 90 MP (10.000 × 9.000), ICC sRGB e alfa 127**, foi realmente
  decodificada, convertida e ripada para 72 × 65 pixels, com largura de 2,54 cm em
  72 dpi. O PRT coincide byte a byte e em metadados com uma referência sólida menor
  da mesma proporção/cor/ICC. A prévia 220 × 198 preserva o alfa.
- O smoke do painel executa login, planejamento de duas peças e da arte de 400 MP,
  três uploads/PRTs idênticos sem ICC/com ICC repetido, prévias com marca e encerramento.
  O mesmo script testa o executável Windows no CI.

Os 400 MP validam metadados/admissão; não representam uma promessa de ripar esse
raster em qualquer computador. O teste real de 90 MP usa cor uniforme e saída
pequena para isolar a aceitação da origem; não mede desempenho em toda carga.

Para reproduzir o teste real com as dependências de desenvolvimento instaladas:

```bash
python tools/smoke_large_input.py --output /tmp/large-input-validation.json
python -m pytest -q
```

O teste real usa arquivos temporários e remove as artes/PRTs ao terminar; deixa
somente o relatório JSON solicitado. Use um caminho de saída adequado ao Windows.

[Relatório do teste real](../../benchmarks/campaign_runs/2026-11-10-input-pixels/large-input-validation.json) e [ambiente/código testado](../../benchmarks/campaign_runs/2026-11-10-input-pixels/environment.json).
