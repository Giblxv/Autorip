# Morfologia física, desempenho e confiabilidade

Base: `main` em `1097665bd7f8ffd46b794686d9d6d967acd85e48`.
Patch de origem: `autorip-patch-morph.zip`, fornecido pelo usuário; os módulos foram
inspecionados e adaptados, sem executar o script de substituição textual do ZIP.

## Problema e comportamento final

O fechamento e o recuo de branco usavam kernels retangulares grandes, lentos em
720 × 2400 dpi e com efeito diferente em diagonais. `autorip.morph` passa a usar
transformada euclidiana de distância (EDT) com amostragem física nos dois eixos.
Máscaras vazias permanecem vazias, objetos nas bordas são preservados no fechamento
e a erosão trata o exterior como fundo. O halo entre tiras usa raio arredondado para
cima, evitando recortar a influência da morfologia nas emendas.

O disco altera intencionalmente a geometria do branco nos cantos e pode alterar a
quantidade de tinta em relação ao kernel retangular. Formato PRT, ordem dos canais,
DPI, espelhamento e transformação ICC permanecem os da versão de base. O motor
libera os buffers de uma tira antes de alocar a próxima e contabiliza 96 bytes por
pixel no orçamento de memória, incluindo o trabalho adicional de EDT.

Uploads manuais agora são escritos em `.upload.part`, validados, associados a um
sidecar `.request.json` atômico com largura e SHA-256 e só então publicados para a
fila. Após reinício antes ou durante o RIP, a largura solicitada é restaurada. Um
sidecar inválido ou uma imagem alterada são preservados para revisão, sem gerar
PRT com escala presumida. Uploads antigos sem sidecar mantêm a compatibilidade.
O sidecar é removido somente depois de arquivar a entrada; bloqueios transitórios
na limpeza são retentados. Uploads parcialmente recebidos não são tratados como
artes prontas pelo watcher.

No painel, filas sem mudanças não são reconstruídas, miniaturas autenticadas
compartilham um cache limitado a 64 entradas/60 segundos e as consultas não se
sobrepõem. A CSP permite os blobs dessas imagens, mantendo a autenticação. A perda
de conexão aparece explicitamente. O interruptor funciona com teclado, o progresso
converte corretamente a fração 0–1 para porcentagem e o formulário aceita casas
decimais sem truncar intervalos ou margens. A grade do modal adapta-se a telas
estreitas. Foram reduzidos fundo decorativo e movimento permanente, corrigido o
contraste dos títulos ciano/amarelo e substituída a celebração que cobria o painel
por aviso discreto. A preferência de movimento reduzido é respeitada.

A janela nativa oferece acesso ao painel e mostra estado automático, rede e fila.
Os eventos do servidor passam por uma fila; somente a thread principal acessa os
widgets Tk.

## Módulos opcionais do ZIP

- `nesting`: empacotamento por rectpack, ainda sem composição de imagens/PRT.
  Valida dimensões, quantidades e limites; quantiza peças para cima e folha para
  baixo para não exceder a área disponível. Resultados não compartilham listas
  mutáveis de itens não posicionados. rectpack 0.2.2: Apache-2.0,
  <https://github.com/secnot/rectpack>.
- `bgremove`: adaptador de rembg/ONNX com modelo local obrigatório. Normaliza EXIF,
  limita pixels, aplica corte de alfa e publica PNG sem sobrescrever o destino.
  rembg: MIT, <https://github.com/danielgatis/rembg>; ONNX Runtime: MIT,
  <https://github.com/microsoft/onnxruntime>. O modelo é fornecido pelo operador;
  sua compatibilidade e licença precisam corresponder ao uso escolhido.

Esses módulos não são importados pelo programa padrão, não adicionam dependências
à instalação básica e não são incorporados ao executável padrão. O teste de
bgremove usa uma sessão simulada; não foi executada inferência de modelo real.
A instalação dos extras pode exigir internet; a inferência usa o modelo local.

## Desempenho medido

Linux, Python 3.12.14, NumPy 2.5.4; imagem sintética, sem ICC de saída; uma rodada de
aquecimento e mediana de três execuções por versão. Os números variam com hardware,
carga do sistema, dimensões, transparência e perfil ICC. O branco mudou de geometria;
portanto este comparativo mede o fluxo anterior contra o novo fluxo, não dois
resultados de branco idênticos.

| Operação | Antes | Depois | Ganho |
| --- | ---: | ---: | ---: |
| Branco, máscara 640 × 1700 | 1,195 s | 0,148 s | 8,08× |
| RIP completo, arte 5 × 3,75 cm, 720 × 2400 dpi | 7,450 s | 1,698 s | 4,39× |

Sem branco, os PRTs da comparação foram idênticos byte a byte. Isso não é garantia
de ganho igual para todas as artes ou de qualidade física de impressão.

Reproduzir a comparação com a base:

```bash
git show 1097665:autorip/engine.py > /tmp/autorip-engine-baseline.py
python benchmarks/benchmark_rip.py --baseline /tmp/autorip-engine-baseline.py --repeat 3
```

Resultados: [JSON](../../benchmarks/morph-results-linux.json).

## Testes

A base tinha 197 testes aprovados. A suíte final local passou com **220 testes**
em 35,64 s. Foram adicionadas regressões de disco físico
contra kernel de referência, máscara vazia, bordas, continuidade entre tiras,
recuperação da largura antes/durante RIP, persistência indisponível, parâmetros
corrompidos, identidade da imagem, limpeza com bloqueio temporário, eventos Tk e
módulos opcionais. Executar:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

No Chromium/Playwright foram exercitados criação/login de senha, configuração com
intervalo de 0,25 s, interruptor por teclado, upload real, PRT, miniaturas protegidas,
barra a 100%, estabilidade do DOM e dos downloads quando ocioso, perda/retorno de
conexão e telas de 390 e 320 px. Sem erros JavaScript ou violações de CSP no fluxo.
As duas miniaturas foram baixadas uma vez cada e não voltaram a ser requisitadas
no período ocioso observado. A grade mobile mediu 312 px de largura visível e de
conteúdo. A preferência de movimento reduzido resultou em zero animações ativas.

**Não validado fisicamente** em PrintExp/Hoson ou impressora. O teste local da
janela nativa usa widgets simulados; os testes do GitHub Actions cobrem Windows e
Linux, mas não substituem uma avaliação visual do executável no Windows.

## Compatibilidade e rollback

Nenhuma release é publicada por esta alteração. As configurações existentes não
são migradas. Para reverter, restaure os arquivos de código da base; não apague as
pastas de produção ou os journals. Antes de usar uma versão antiga sem suporte ao
novo sidecar, conclua ou revise uploads pendentes: ela não restaura sua largura
manual. Uma reversão muda novamente a geometria do branco de novos PRTs.
