# Estudo dos RIPs e prioridades para o AutoRIP

Data: 13/11/2026. Base inspecionada: `ed9ac95153aa01bb84e461e555866d21e394bf8f`, versão 0.8.25.

A recomendação é começar pela fila de impressão e pelo agente PrintExp, desenvolver processamento de origens grandes com orçamento global de memória e, depois, ampliar preflight, presets de produção e gerenciamento de cor. A execução por tiras, os caches limitados e o planejamento MaxRects existentes oferecem uma base para essa evolução.

Este é o estudo inicial de arquitetura e comportamento documentado. Foram consultadas páginas oficiais de sete famílias de RIPs e inspecionado o código do AutoRIP. A engenharia reversa experimental dos executáveis e das trocas FlexiPrint–PrintExp depende das instalações e amostras correspondentes. Algoritmos internos dos concorrentes e ganhos comparativos continuam pendentes de ensaio.

## Referências e recursos observados

A seleção abaixo reúne produtos de referência; não estabelece ranking de participação de mercado. Recursos podem depender de edição, módulo adicional, versão e equipamento.

| Família e fonte consultada | Recurso descrito pelo fornecedor | Aplicação proposta no AutoRIP |
| --- | --- | --- |
| [SAi Flexi](https://www.thinksai.com/products-flexi/) e [Flexi DTF Pro](https://www.thinksai.com/products-flexi-dtfpro/) | Production Manager, encaixe por contorno e divisão em painéis; gerenciamento de cor; prévia e ajustes da base branca no DTF | Presets versionados, prévia das separações e comparação de branco; evoluir o encaixe retangular para ocupação por contorno |
| [ONYX Thrive](https://onyxgfx.com/products/onyx-thrive/) | Fluxo PDF com Adobe PDF Print Engine, QuickSets, hot folders, processamento paralelo de trabalhos e encaixe | Separar preparação, rasterização e saída; presets por destino; admissão de trabalhos de acordo com memória disponível |
| [CalderaRIP](https://www.caldera.com/solutions/calderarip-your-rip-software-for-mac-and-linux/) | Perfis ICC, recalibração, hot folders, preparação e controle de dispositivos de impressão e corte | Receita de mídia/tinta/resolução, trilha de calibração e preparação uniforme para diferentes destinos |
| [Ergosoft RIP](https://ergosoft.net/en/products/ergosoft-rip) | Preparação de trabalhos, substituição de cores especiais, automação por hot folder, dados ERP/CSV e códigos de barras | Ticket estruturado por trabalho e regras de entrada, com histórico de alterações e resultado |
| [Fiery Digital Factory DTF](https://www.fiery.com/products/digital-factory-dtf/) | Gestão de filas, ferramentas DTF e módulos de classificação de trabalhos, calibração e DeviceLink | Regras de roteamento por mídia/destino, presets reprodutíveis e futura calibração por medição. Os módulos adicionais devem ser tratados separadamente |
| [Wasatch SoftRIP Automation](https://wasatch.com/solutions/automation/) | API, integração com sistemas de negócio, exemplos de scripts, encaixe e balanceamento por hot folders | API de produção para desktop, aplicativos móveis e sistemas externos; conectores independentes do motor |
| [PrintFactory WorkFlow](https://printfactory.cloud/workflow/) e [DTF](https://printfactory.cloud/dtf/) | Preflight, fluxos configuráveis, entradas por hot folder e banco de dados, encaixe e recursos de branco/meio-tom DTF | Fluxos de produção verificáveis, preflight antes do RIP e receitas explícitas de branco e meio-tom |

Estas descrições são capacidades publicadas, não resultados de benchmark. Não se deduz uso de GPU, implementação de tiling ou protocolo PrintExp a partir dessas páginas. O [índice de fontes](rip-study-2026-11-13/sources.json) registra URLs finais, respostas HTTP e hashes dos conteúdos consultados. As URLs antigas de CADlink retornaram HTTP 503; a página oficial atual da Fiery foi consultada com sucesso.

## Situação observada no repositório

- [`engine.py`](../../autorip/engine.py) já usa tiras com halo, concorrência limitada, ICC, meio-tom de 2 bits, geração de branco e caminho RGB opaco. A origem ainda é decodificada integralmente em `_load_source`; `_prepare_resampling` pode criar outro raster completo `RGBa`. O orçamento de 512 MiB das tiras não limita todo o consumo da origem.
- [`server.py`](../../autorip/server.py) limita admissão e mantém a fila operacional em memória. Existem journals de recuperação de arquivos e de publicação; um ledger durável unificado para os estados RIP → transferência → PrintExp ainda precisa ser projetado.
- [`paths.py`](../../autorip/paths.py) publica arquivos completos atomicamente sem sobrescrever destinos. Essa propriedade deve ser preservada até o computador receptor.
- [`sheet_nesting.py`](../../autorip/sheet_nesting.py) e [`layout.py`](../../autorip/layout.py) oferecem encaixe retangular e prévia. Encaixe por contorno e descarte de áreas transparentes exigem outro modelo geométrico.
- [`agent/print_agent.py`](../../agent/print_agent.py) opera a interface do PrintExp via UI Automation. A integração TCP com o receptor PrintExp/NWReceive permanece pendente de identificação do protocolo.
- O contrato de cor atual é CMYK com planos de branco, profundidade PRT de 2 bits e mapeamentos específicos. Canais fluorescentes, verniz e novas modalidades de gotas exigem um contrato de dispositivo e validação próprios.

As campanhas anteriores já verificaram configurações de tiras, trabalhadores, buffers e cálculos NumPy. A campanha encerrada em 12/11 completou 100 rejeições consecutivas sem ganho de produção. O estudo propõe novos problemas e arquiteturas; a contagem anterior não é uma demonstração de desempenho máximo para todas as cargas possíveis.

## Achados reproduzidos no agente

O diagnóstico utilizou SQLite e arquivos temporários com driver simulado; nenhuma conexão de rede ou impressão real foi realizada. O [resultado estruturado](rip-study-2026-11-13/agent-findings.json) e o [reprodutor](rip-study-2026-11-13/reproduce_agent_findings.py) acompanham este estudo.

| Achado | Observação no código e na simulação | Consequência e requisito |
| --- | --- | --- |
| Revisão manual pode reenviar o trabalho | `process()` só ignora `concluido`. Duas chamadas com confirmação expirada terminaram em `revisao_manual` e produziram duas solicitações simuladas de impressão | P0: estados incertos devem bloquear novas tentativas até reconciliação explícita |
| Confirmação não identifica o trabalho | `wait_confirmation()` procura palavras em todos os textos visíveis. Um trabalho antigo com `completed` confirmou o trabalho atual ainda em espera | P0: vincular confirmação a identificador, destino e transição temporal do trabalho atual |
| PRT pendente é relido repetidamente | Duas inspeções do mesmo PRT pendente recalcularam o SHA-256 duas vezes. `stable()` também espera `stable_seconds` por arquivo em cada passagem | P1: spool imutável, fingerprint persistido, detecção de mudanças e hash reutilizável com validação de identidade |

O padrão atual `auto_print=false` permite preparar essas correções antes de habilitar a operação automática. Há ainda uma janela entre `start_print()` e a gravação de `impressao_solicitada`; a intenção precisa ser persistida antes da ação externa. A automação por interface deve ser vinculada ao processo correto, inclusive os diálogos de abertura.

No cenário configurado com espera de três segundos, 1.000 arquivos pendentes acrescentam aproximadamente 3.000 segundos de espera por passagem, além do hash e do I/O. Essa é uma estimativa derivada do laço atual, não uma medição física de produção.

## Backlog proposto

Prioridade expressa a ordem de implementação. O impacto é uma hipótese a medir, não uma promessa de velocidade.

| ID | Prioridade | Mudança concreta | Integração e critério de aceite |
| --- | --- | --- | --- |
| RIP-01 | P0 | Ledger de impressão, bloqueio de estados incertos e confirmação correlacionada | `agent/print_agent.py`, API e armazenamento: duas passagens e reinício em estado incerto geram zero novas solicitações; reimpressão deliberada recebe novo ID |
| RIP-02 | P1 | Ticket imutável por trabalho e presets versionados | Fixar perfil ICC e seu hash, tinta/mídia, DPI, canais, branco, espelhamento, cópias e destino; alteração posterior das configurações não modifica o trabalho aprovado |
| RIP-03 | P1 | Orçamento global de memória e leitor de origem por regiões | Começar com TIFF/BigTIFF em backend opcional; medir RSS nativo, leitura, spill para disco e igualdade do caminho compatível. Tratar orientação, alpha premultiplicado e suporte do filtro nas bordas |
| RIP-04 | P1 | Spool e transporte de arquivos grandes | Publicação atômica, leitura em blocos, fila com contrapressão e integridade; arquivo de vários GiB não pode exigir um buffer do tamanho do arquivo |
| RIP-05 | P1 | Evitar varreduras e hashes repetidos no agente | Manifesto de saída e fingerprints de arquivos já estáveis; comparar ciclos de fila com 1, 100 e 1.000 pendências sem executar impressão |
| RIP-06 | P2 | Preflight e prévia por separação | Mostrar branco, CMYK, tamanho físico, DPI, perfil/destino e regiões transparentes; preflight deve antecipar erros já detectados pelo motor |
| RIP-07 | P2 | Nesting por ocupação real e receitas de gang sheet | Contornos derivados do alpha com dilatação física para espaçamento; medir aproveitamento e tempo com 10/100/1.000 peças e validar ausência de colisões após rotações |
| RIP-08 | P2 | Linearização e calibração física | Curvas por tinta, mídia e modo de impressão; comparação por instrumento e amostra física, mantendo branco e cores especiais controlados |
| RIP-09 | P2 | API de produção compartilhada pelos clientes | Aplicativos móveis consultam e aprovam tickets; transferência e estado de impressão pertencem ao servidor/agente, com paginação e atualização incremental |
| RIP-10 | P3 | Entrada PDF e cores especiais | Escolher motor e licenciamento, avaliar transparências, fontes e overprint. Aumento de formatos depende de preflight e de testes de referência |
| RIP-11 | P3 | Backend compilado/GPU ou multiprocesso | Promover somente se reduzir o custo do estágio dominante e o tempo total; incluir cópias entre processos/GPU e divergências nas bordas do meio-tom e morfologia |

RIP-03 exige atenção especial: JPEG/PNG comuns não oferecem o mesmo acesso aleatório de um TIFF em tiles. Decodificação sequencial ou staging em disco pode ser necessária. Um leitor alternativo que produza pixels diferentes do Pillow deve permanecer em modo separado, com receita e validação de qualidade próprias.

## Protocolo de engenharia reversa experimental

1. **Inventariar o ambiente:** produto, versão, edição/módulos, CPU/RAM/disco, impressora, controladora, tinta, mídia, firmware, perfil ICC e receita completa. Obter uma referência PrintExp que já aceite o PRT.
2. **Construir entradas controladas:** RGB/RGBA, ICC embutido, alpha em gradiente, transparência por paleta, DPI anisotrópico, EXIF, larguras sem alinhamento, etiquetas, margens vazias, bordas de branco e origens de 90 MP ou maiores. Usar desenhos sintéticos e amostras de produção adequadas ao ensaio.
3. **Observar o fluxo:** criação e alteração dos arquivos temporários, ordem das operações, leitura/escrita, consumo de RAM, fila e mensagens do receptor. A primeira coleta de rede deve identificar os processos e separar RIP → receptor de receptor → placa.
4. **Variar um parâmetro por vez:** tamanho/nome do trabalho, comprimento do arquivo, número de cópias, DPI, ordem de canais e posição na folha. Comparar cabeçalhos, metadados e comportamento; registrar hipóteses ainda não demonstradas.
5. **Decodificar saídas quando possível:** geometria, alinhamento por linha, canais, cobertura de tinta e máscara branca. Diferenças de dithering entre fabricantes são esperadas; a comparação entre produtos deve incluir qualidade e medição física. Mudanças compatíveis do AutoRIP continuam sujeitas à igualdade de bytes com sua própria base.
6. **Reimplementar componentes identificados em módulos independentes:** manter especificação de comportamento, fixtures e origem de cada inferência. Recursos descritos comercialmente não demonstram o algoritmo ou o protocolo usados internamente.

Instalações dos RIPs comerciais, binários e capturas reais FlexiPrint–PrintExp não estavam disponíveis nesta etapa. Os experimentos acima são trabalho futuro definido, e não uma alegação de engenharia reversa de binários já concluída.

## Medição e promoção

Medir separadamente: tempo até início, decode/orientação, ICC, resize, branco/morfologia, meio-tom, empacotamento, sincronização/publicação, transferência e espera de fila. Registrar tempo total, MP de origem/saída, bytes produzidos, RSS nativo máximo, I/O e taxa de transferência. `tracemalloc` isoladamente não captura toda a memória de Pillow, NumPy e LittleCMS.

Usar processos novos e ordem balanceada; separar cargas quentes e frias e documentar afinidade de CPU. Para ganho pequeno, usar pelo menos 15 pares, confirmação, controle A/A e distribuição de tempos; executar validação fora do cronômetro. A aceitação considera regressões por carga, pico de memória e comparação cumulativa com a base, além da média.

Os testes de cor e de economia de branco devem incluir cobertura, qualidade visual e, quando aplicável, ΔE00 medido. Uma alteração de intenção de cor não equivale a uma otimização compatível de desempenho. A velocidade da impressora e a latência de transferência devem ser registradas separadamente da rasterização.

## Próxima entrega recomendada

Implementar RIP-01 e o ticket RIP-02 antes de habilitar envio automático; depois seguir os marcos do [plano PrintExp](../PRINTEXP-INTEGRACAO-PLANO.md). O estudo inicial e o plano podem ser revisados agora; a validação de protocolo e de impressão depende dos dados da instalação.
