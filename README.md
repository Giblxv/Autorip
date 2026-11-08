# AutoRIP 0.8.2 — automação de pré-impressão DTF / DTF UV

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

Também existe o workflow manual **Build Windows** no GitHub Actions. Ele compila em Windows, gera os dois arquivos e publica ambos como artefato baixável por 14 dias. O executável one-file é portátil, mas o instalador é a opção recomendada para instalação, atalhos e configuração inicial.

O navegador é somente a interface opcional do painel; o RIP, a conversão ICC, o meio-tom e a geração do `.PRT` rodam localmente no computador. Para deixar o AutoRIP trabalhando como serviço de hot-folder, sem abrir navegador, use o atalho **AutoRIP (segundo plano)** criado pelo instalador ou execute `AutoRIP.exe --headless`. Isso reduz o uso de interface, mas não altera a matemática do RIP: a velocidade depende principalmente de CPU, memória, resolução, tamanho da arte e perfil ICC.

O instalador é por usuário e não precisa de privilégios administrativos. A configuração inicial fica em `%APPDATA%\AutoRIP\autorip.json`; atualizações não sobrescrevem a configuração existente.

### Python / linha de comando

```bash
python -m pip install -r requirements.txt
python -m autorip                         # abre o painel local
python -m autorip --icc perfil.icc --width-cm 20 arte.png
python -m autorip --force arte.png        # reprocessa intencionalmente uma entrada já concluída
python -m autorip --watch                 # observa a hot-folder
python -m autorip --once                  # processa a hot-folder uma vez
AutoRIP.exe --headless                    # Windows: worker local sem abrir navegador
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
- Uploads aceitam PNG, TIFF e JPEG de até 200 MiB e 80 milhões de pixels; a área de uploads pendentes tem quota agregada de 1 GiB e preserva 128 MiB de espaço livre. Entradas de hot-folder também são limitadas por pixel.
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

## Histórico recente

- **0.8.1:** journal com hash do PRT antes da publicação, recovery seguro do CLI posicional, sidecar/outbox recuperáveis e idempotentes, proteção contra PRT homônimo e liberação de locks antigos de saída após jobs ativos.
- **0.8.2:** modo `--headless`/`--no-browser` para rodar como worker local, sem abrir navegador; atalho de segundo plano e inicialização automática no Windows.
- **0.8.0:** publicação PRT/arquivos no-clobber por rename atômico ou criação exclusiva; locks de hot-folder/saída; histórico recuperável, retry/backoff e cópia cross-volume; limite de nomes, quota agregada de uploads e proteções do painel; sidecar de dimensões, URLs de miniaturas seguras, endpoint de logo confinado e CI.
- **0.7.0:** fila durável de notificações com retry parcial; isolamento de credenciais; URLs/redirects de integração protegidos; validação de configuração e do PRT; hot-folder recuperável e sem colisões; fila de impressão mais segura; limites de entrada/fila; testes automatizados portáteis.
- **0.6.0:** fila local de impressão com miniaturas, registro do trabalho e gravação do PRT em arquivo temporário antes da publicação.
