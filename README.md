# AutoRIP 0.8.16 — automação de pré-impressão DTF / DTF UV

O AutoRIP organiza uma etapa de pré-impressão: importa artes raster, converte cores, prepara a base branca e gera arquivos `.PRT` para fluxo com PrintExp. Ele não substitui o software/driver do fabricante e **o formato PRT deste projeto foi inferido de uma referência, não de uma especificação oficial**. Antes de produção, valide em uma impressora de teste: abertura no PrintExp, ordem de canais, dimensão, escala, branco, orientação e densidade. Comece com material de baixo custo; o arquivo pode não ser compatível com todo equipamento.

## Fluxo de processamento

`PNG / TIFF / JPEG → orientação EXIF → conversão ICC (se configurada) → meio-tom de 2 bits → CMYK + base branca → arquivo PRT`

O formato de saída configurado por padrão usa 12 canais, 720 × 2400 dpi, canais de cor K/C/M/Y e branco no plano 4. Esses parâmetros e o perfil precisam corresponder à impressora, tinta, filme e PrintExp utilizados. A conversão sem perfil ICC é genérica; para consistência de cor, configure um perfil apropriado. Um perfil inexistente ou inválido é informado e interrompe o RIP — não há fallback silencioso.

A base branca respeita o alfa/transparência e oferece controles de densidade, recuo (choke) e preenchimento de furos. Não é um removedor de fundo: arquivos com fundo opaco continuam tendo fundo opaco. Prefira artes com transparência real e revise a máscara antes de imprimir.

## Instalação e execução

### Windows

1. Instale Python 3.10+ e Inno Setup 6.
2. Execute `build_windows.bat` para gerar o executável one-file `dist\AutoRIP\AutoRIP.exe` e, com o Inno Setup 6 instalado, o instalador único `Output\AutoRIP_Setup.exe`.
3. Para preparar o pacote em um computador conectado e compilar depois sem internet, use `preparar_offline.bat` e, no computador de build, `build_windows_offline.bat`.

Também existe o workflow **Build Windows** no GitHub Actions. Em uma tag `v*`, ele compila em Windows e publica uma release com `AutoRIP.exe`, `AutoRIP_Setup.exe` e `SHA256SUMS.txt`; a release atual está em [v0.8.16](https://github.com/Giblxv/Autorip/releases/tag/v0.8.16). O executável one-file é portátil, mas o instalador é a opção recomendada para instalação, atalhos e configuração inicial.

O RIP, a conversão ICC, o meio-tom, as integrações e a geração do `.PRT` rodam localmente no computador usando a conexão de internet do próprio Windows quando necessário. O executável Windows inicia por padrão em uma pequena janela nativa de status, sem abrir navegador. Para isso, use o atalho **AutoRIP (modo direto)** ou execute `AutoRIP.exe --direct`; `--headless` continua aceito como alias. O painel web opcional oferece controles da fila, configurações e planejamento da folha; abra-o com `AutoRIP.exe --web`. A velocidade depende principalmente de CPU, memória, resolução, tamanho da arte e perfil ICC.

O botão **⏻ Encerrar** do painel encerra o servidor local de forma segura. Quando não há produção ou integrações ativas, o painel também encerra automaticamente o servidor depois de aproximadamente 15 segundos sem receber o navegador; o processamento pendente e o modo automático mantêm o servidor ativo.

O instalador é por usuário e não precisa de privilégios administrativos. A configuração inicial fica em `%APPDATA%\AutoRIP\autorip.json`; atualizações não sobrescrevem a configuração existente. Em executáveis Windows, a opção **Atualizar automaticamente pelo GitHub** vem ligada: o AutoRIP consulta no máximo uma vez por dia, aceita somente a release oficial, valida o SHA-256 e executa o instalador silencioso. Desative-a em Configurações se preferir atualizar manualmente; o modo offline nunca consulta a rede.

### Aplicativo móvel

O cliente Android está em [`mobile/`](mobile/README.md). O cliente Flutter para iPhone/iPad está em [`mobile_ios/`](mobile_ios/README.md); ele abre o painel do servidor em WKWebView e mantém localmente até cinco endereços recentes. O teste e a análise Dart rodam com `flutter test` e `flutter analyze`; gerar/assinar o IPA exige macOS com Xcode.

O instalador Windows e a área **Ajuda** do painel exibem QR codes móveis: Android abre a prévia 0.2.0 com APK padrão e variante Optimized de teste; iPhone/iPad abre o guia até haver IPA assinado publicado. Para conectar os apps à instância local, use **Conectar celular** no painel para gerar o QR de endereço; ele não inclui a senha.

### Python / linha de comando

```bash
python -m pip install -r requirements.txt
python -m autorip                         # abre o painel local
python -m autorip --icc perfil.icc --width-cm 20 arte.png
python -m autorip --force arte.png        # reprocessa intencionalmente uma entrada já concluída
python -m autorip --watch                 # observa a hot-folder
python -m autorip --once                  # processa a hot-folder uma vez
AutoRIP.exe --direct                      # Windows: janela nativa e worker local
```

O painel atende somente em `127.0.0.1`. O modo automático lê a hot-folder, espera os arquivos estabilizarem, reivindica cada arquivo antes do RIP e arquiva a entrada em concluídos ou erros. Um journal local grava o SHA-256 do PRT temporário **antes** da publicação; na retomada, o AutoRIP só associa uma saída ao job se o hash exato e o cabeçalho PRT forem válidos. Um arquivo homônimo não é prova de conclusão. Após uma interrupção, a retomada recria o sidecar de dimensões e reconstitui a outbox de forma idempotente antes de arquivar a entrada. Se o estado for ambíguo, o AutoRIP preserva a entrada para revisão ou a encaminha para erros, em vez de declarar falsamente que um PRT concorrente é seu.

O comando posicional também mantém um journal por entrada em `.autorip_manual` dentro da pasta de saída: uma repetição idêntica é ignorada se já houver sucesso, e um PRT publicado antes de um crash é recuperado por hash sem duplicação. Use `--force` somente quando quiser deliberadamente gerar outra saída; colisões recebem sufixos e não sobrescrevem PRTs existentes. Se o destino estiver indisponível, o programa tenta uma pasta de recuperação e repete a operação de arquivamento com backoff. Ao mudar a hot-folder, trabalhos interrompidos nas pastas anteriores são preservados e recuperados após reinício. Movimentos entre volumes usam cópia temporária e publicação final sem sobrescrita.

Configure `hot_folder`, `output_folder`, `printed_folder`, `done_folder` e `error_folder` em caminhos distintos e não sobrepostos; aliases por symlink também são rejeitados para evitar ciclos de reprocessamento. Arquivos com o mesmo nome recebem sufixos. O motor e o painel nunca substituem arquivos concorrentes ao publicar `.PRT`. O painel mantém locks de instância, hot-folder e saída; `--watch` usa locks de hot-folder e saída; o CLI posicional mantém lock de saída. Ao alterar a pasta de saída no painel, o lock antigo continua retido enquanto um job ativo a utiliza e é liberado quando ele termina. O painel e os modos CLI gravam sidecar `.meta.json` com dimensões da fila; ele não é lido pelo PrintExp.

## ICC e dados locais

Selecione o ICC da própria impressora em **Configurações** ou na página do instalador. O AutoRIP não inclui perfis proprietários no repositório/instalador. O perfil fornecido para avaliação foi validado localmente, mas não é redistribuído: configure no seu computador a cópia que você está autorizado a usar.

A configuração da conta e as credenciais das integrações ficam no diretório local do AutoRIP. Em sistemas POSIX, o arquivo é salvo com permissão restrita (`0600`); no Windows, ele herda as permissões da conta. Os segredos não são devolvidos pela API do painel e os campos são write-only. Não publique nem compartilhe `autorip.json`, `auth.json` ou `outbox.json`.

## Segurança, privacidade e rede

- O modo offline vem **ligado por padrão**. O RIP local, a geração de `.PRT` e a fila de impressão funcionam sem rede.
- O servidor local aplica senha de 8 a 128 caracteres, limite de tentativas, token de sessão em memória, validação de origem/CSRF e limites de upload/fila.
- Uploads aceitam PNG, TIFF e JPEG sem quota artificial de bytes; continuam limitados por 80 milhões de pixels, validação do formato e 128 MiB de espaço livre para não comprometer o sistema. Entradas de hot-folder também são limitadas por pixel.
- Integrações externas só funcionam se configuradas e com o modo offline desligado. Tokens não são incluídos em URLs Trello; redirects de APIs com credenciais são bloqueados. Downloads Trello são limitados, validados como imagem e restritos a hosts permitidos.
- Notificações são enfileiradas localmente antes do envio e retentadas por serviço. O AutoRIP conserva avisos pendentes caso um canal falhe ou seja desativado.
- O agente de IA é opcional e só é chamado quando solicitado. Ele recebe parâmetros técnicos permitidos, não chaves, caminhos locais, nomes de arquivo ou conteúdo do registro; pode pesquisar a web e apenas sugere mudanças, sem alterar a configuração.

Desligar o modo offline permite tráfego externo para os serviços que você configurou. Revise os endpoints, as credenciais e as políticas desses serviços antes de habilitá-los.

## Integrações opcionais

Trello pode buscar anexos de imagem de uma lista de entrada e criar cartão de conclusão; Notion, Jira e webhook recebem avisos de trabalhos concluídos. O agente de IA fornece sugestões técnicas. O AutoRIP não envia a imagem original nem faz upload do `.PRT` para essas integrações.

## Testes

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Os testes usam imagens sintéticas e servidores HTTP locais simulados; não exigem Drive, credenciais, perfil ICC externo nem impressora. Para o perfil e equipamento reais, faça também a validação física descrita no início deste README.

O workflow do GitHub Actions executa a mesma suíte em pushes e pull requests para `main`.

## Morfologia e desempenho

A versão 0.8.14 incorpora o [patch de morfologia e desempenho](docs/refinements/MORPH-PERFORMANCE.md), que prepara
branco com disco físico por EDT, preserva a largura de uploads após reinício e
melhora o painel. A alteração do branco modifica sua geometria nos cantos; faça
uma prova física antes de usar essa versão em produção.

## Planejamento de folha

No painel, use **Hot folder → Planejar folha**. Selecione as artes, informe
quantidades e larguras, ajuste a largura da folha (até 58 cm), margem e espaçamento
e clique em **Calcular encaixe**. A rotação de 90° é opcional. A altura de cada arte
mantém sua proporção física, considerando os DPI e a orientação lidos do cabeçalho.

O planejador mostra posições, altura e aproveitamento da folha e exporta a prévia
SVG e o planejamento JSON. Usa MaxRects offline, sem precisar instalar `rectpack`,
e permite até 100 peças por cálculo, contando as cópias. O planejamento preserva
as fontes e a fila: não compõe nem envia um PRT. [Detalhes e API](docs/refinements/NESTING.md).

A API anterior de encaixe em folhas fixas continua disponível em `autorip.nesting`
com `nest_sheets` e com as chamadas antigas a `nest`; ela ainda usa `rectpack`.
`autorip.bgremove` é uma biblioteca auxiliar sem ligação ao painel ou à composição
PRT. Instale `requirements-optional.txt` somente para essas funções opcionais.
A remoção de fundo exige `model_path` apontando para um modelo ONNX local
compatível; o AutoRIP não baixa modelos automaticamente.

## Histórico recente

- **0.8.16:** QR autenticado para conexão móvel, Ajuda e QR de distribuição Android/iOS no instalador; atualização dos clientes de teste Android/iOS. [Notas da versão](docs/releases/v0.8.16.md).

- **0.8.15:** planejamento de folha no painel com MaxRects offline, prévia e exportação SVG/JSON; RIP com paralelismo limitado e menos buffers de imagem; caches limitados de ICC/prévias; admissão em lote e controles de fila estáveis. [Notas da versão](docs/releases/v0.8.15.md).

- **0.8.14:** fila manual com hot folder, pausa/retomada/cancelamento seguro entre tiras, upload sem quota artificial de bytes e interface psicodélica com animações pausáveis em segundo plano e ajustadas para touch.

- **0.8.13:** morfologia circular em unidades físicas por EDT, recuperação da largura manual, filas e miniaturas mais leves, painel acessível e acesso às configurações pela janela nativa. No benchmark sintético documentado, o RIP passou de 7,45 s para 1,70 s.

- **0.8.1:** journal com hash do PRT antes da publicação, recovery seguro do CLI posicional, sidecar/outbox recuperáveis e idempotentes, proteção contra PRT homônimo e liberação de locks antigos de saída após jobs ativos.
- **0.8.2:** modo `--headless`/`--no-browser` para rodar como worker local, sem abrir navegador; atalho de segundo plano e inicialização automática no Windows.
- **0.8.3:** encerramento seguro pelo painel e atalhos explícitos de modo direto no menu Iniciar e na área de trabalho.
- **0.8.4:** executável Windows nativo por padrão, integrações locais sem navegador e painel web apenas com `--web`.
- **0.8.5:** atualização automática opcional por releases do GitHub, com allowlist, limite de download e verificação SHA-256 antes do instalador.
- **0.8.6:** tratamento fail-safe quando a rede ou a API do GitHub falha antes do download.
- **0.8.7:** janela nativa informa quando o worker está ativo e mostra o motivo quando outra instância ou configuração impede a inicialização.
- **0.8.0:** publicação PRT/arquivos no-clobber por rename atômico ou criação exclusiva; locks de hot-folder/saída; histórico recuperável, retry/backoff e cópia cross-volume; limite de nomes, quota agregada de uploads e proteções do painel; sidecar de dimensões, URLs de miniaturas seguras, endpoint de logo confinado e CI.
- **0.7.0:** fila durável de notificações com retry parcial; isolamento de credenciais; URLs/redirects de integração protegidos; validação de configuração e do PRT; hot-folder recuperável e sem colisões; fila de impressão mais segura; limites de entrada/fila; testes automatizados portáteis.
- **0.6.0:** fila local de impressão com miniaturas, registro do trabalho e gravação do PRT em arquivo temporário antes da publicação.
