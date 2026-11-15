# Tiras 1:1 sem reconverter a imagem RGBA inteira

Base: `52d07e2`, AutoRIP 0.8.33. O refinamento atua quando largura e altura da
arte em pontos coincidem com os pixels da origem orientada. Margens e etiquetas
continuam sendo acrescentadas pelo mesmo renderizador.

## Custo eliminado e equivalência

O preparo anterior preserva RGBA em 1:1 porque o Pillow pode copiar uma região
que coincide com a imagem inteira sem quantizar cores com alfa parcial.
Mas, para uma região parcial, `resize(..., LANCZOS, box=...)` converte toda a
origem para `RGBa` antes de extrair a tira, mesmo em escala 1:1. Em uma arte
alta, essa conversão integral se repete em cada tira e em vários workers.

O motor agora recorta a região inteira de pixels correspondente à tira.
Para RGBA parcial, mantém o ciclo `RGBA → RGBa → RGBA` na região privada,
preservando exatamente a quantização anterior, inclusive cores sob alfa zero.
Para a região que cobre toda a imagem, mantém os pixels sem esse ciclo.
RGB/RGBa mantêm o resize anterior. Origem e resultados têm memória separada;
os buffers intermediários da conversão são fechados também em falhas.

Redimensionamentos e outros modos continuam usando o mesmo Lanczos e box.
Acima de `2**24` em algum eixo, permanece o resize original, pois seu box usa
float32 e nem todos os inteiros maiores são exatos. É uma condição do atalho,
não um novo limite de imagem. Não altera resolução, grade/halo das tiras,
threads, canais, ICC, retícula, branco, mirror, etiquetas, fila ou formato PRT.

## Medição

Dois ensaios independentes, sete pares alternados AB/BA por cenário, com
aquecimento e sem pytest concorrente. Linux/Python 3.12.14, Pillow 13,
NumPy 2.5.4, quota de quatro CPUs e cinco CPUs informadas pelo sistema.

O cronômetro cobre `Rip.process`: abrir e preparar a origem, renderizar,
gravar, fsync e publicar o PRT. A instância Rip é reutilizada como no servidor;
construção inicial, upload, espera de hot-folder, prévias, journal e hash de
conferência não entram no tempo. Cada arquivo é comparado por SHA-256 e
metadados. `prt.py` e `morph.py` são idênticos à base, com hashes registrados.

As entradas PNG são sintéticas, com cor e alfa variáveis. A arte alta tem
513 × 8192 pixels; o caso serial tem 513 × 1200 e o caso de uma tira, 129 × 137.
O caso com ICC usa um perfil CMYK instalado no ambiente, identificado pelo hash
do relatório, sem adicioná-lo ao programa. Não representa um perfil da
impressora do usuário.

| Cenário | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| RGBA, uma tira | 2,32 → 2,30 ms | 2,33 → 2,20 ms |
| RGBA serial | 42,19 → 39,17 ms | 42,67 → 39,60 ms |
| RGBA alto | 220,13 → 148,28 ms | 209,57 → 144,84 ms |
| RGBA alto com branco | 407,92 → 332,60 ms | 392,44 → 329,64 ms |
| RGB alto, controle | 109,96 → 108,40 ms | 109,32 → 109,46 ms |
| RGBA redimensionado, controle | 133,96 → 132,72 ms | 135,34 → 130,14 ms |
| RGBA alto com branco e ICC | 499,42 → 417,72 ms | 503,37 → 416,29 ms |

No RGBA alto, o tempo caiu 32,6% e 30,9%; com branco, 18,5% e 16,0%; com
branco e ICC, 16,4% e 17,3%. O caso serial caiu aproximadamente 7,2% nos dois
ensaios. Nesses quatro casos, os intervalos pareados de 95% ficaram acima de
1x nos dois ensaios. Os outros três não demonstraram ganho consistente nas
duas medições. Os controles A/A tiveram razões 1,002x e 1,047x, com intervalos
incluindo 1x; existe variação de alguns pontos percentuais neste ambiente.

Foram comparados **98 pares de PRTs medidos**, todos com SHA-256 e metadados
iguais, além dos aquecimentos, controles e 56 arquivos dos workers de RSS.
Os [dados do ensaio](identity-strips-benchmark.json) e da
[confirmação](identity-strips-confirmation.json) incluem as amostras brutas.

| Pico RSS, caso RGBA alto | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| Sem branco | 159,0 → 142,2 MiB | 172,4 → 149,6 MiB |
| Com branco | 174,2 → 147,4 MiB | 167,7 → 144,6 MiB |
| Com branco e ICC | 168,2 → 147,6 MiB | 175,0 → 148,4 MiB |

O RSS é o pico nativo do processo inteiro em workers novos, duas execuções
por versão/caso. Inclui bibliotecas, decoder, fonte, buffers e render. Os
valores também incluem a leitura do PRT para conferência após o cronômetro.
Variam com alocador, plataforma e concorrência; não são um limite fixo
de RAM nem uma medição no computador Windows do usuário.

## Validação e reprodução

**1.484 testes locais aprovados**, incluindo 29 novos casos: bytes e metadados
de tiras RGB/RGBA/RGBa inteiras/parciais; propriedade da memória; alfa parcial
e RGB oculto sob alfa zero; Lanczos em ampliação/redução e outros modos; fallback
de precisão float32 sem alocar uma imagem gigante; e quatro RIPs completos
comparados ao resize anterior, com uma/quatro threads, branco, margens,
etiquetas, mirror, canais remapeados e dois planos brancos.

```sh
python -m pytest -q
python benchmarks/benchmark_identity_strips.py --baseline-ref v0.8.33 --pairs 7 --icc /caminho/perfil-cmyk.icc --output /tmp/identity.json
python benchmarks/benchmark_identity_strips.py --baseline-ref v0.8.33 --pairs 7 --icc /caminho/perfil-cmyk.icc --output /tmp/identity-confirmation.json
```

Não se afirma aceleração para todas as imagens: o benefício depende da escala
1:1 e da divisão da origem em tiras. Não houve impressão física nem medição de
upload, telefone ou transmissão ao PrintExp.
