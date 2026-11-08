# AutoRIP 0.6 — RIP automatizado para DTF / DTF UV

PNG (com transparência) -> perfil ICC -> meio-tom estocástico (gotas 1/3) -> branco automático -> arquivo .PRT
(12 canais, 720x2400 dpi, ordem das tintas K, C, M, Y; branco no plano 4). O PrintExp imprime o .PRT.

## Gerar o instalador (Windows)
1. Instale Python 3.10+ e Inno Setup 6.
2. Rode `build_windows.bat`  ->  `Output\AutoRIP_Setup.exe`
   Sem internet: `preparar_offline.bat` (1x, com internet) e depois `build_windows_offline.bat`.
O instalador leva tudo dentro; instalar e usar não precisa de internet.

## Instalador
Páginas em português no estilo do programa: boas-vindas, destino, atalhos, pasta de ENTRADA e de SAÍDA, perfil ICC (opcional).
As escolhas viram a configuração inicial em %APPDATA%\AutoRIP\autorip.json (não sobrescreve em atualizações).
Arte do instalador: installer_assets\ (side.bmp, small.bmp, autorip.ico).

## Uso
- Abra o AutoRIP: painel local no navegador (127.0.0.1). Modo automático (hot folder) ou manual (arrastar a arte).
- Configurações protegidas por senha (criada no primeiro acesso): ICC, pastas, branco (densidade, recuo, furos), margens, marca do cliente.
- Linha de comando: `python -m autorip --icc perfil.icc --width-cm 20 arte.png`  |  `python -m autorip --watch`

## Offline
Modo offline (Configurações > Rede) fica LIGADO por padrão: desliga Trello/Notion/Jira/webhook e o agente de IA.
Avisos de trabalhos concluídos ficam numa fila e são enviados quando o modo offline for desligado.

## Integrações (só com modo offline desligado)
Trello (entrada: anexos de imagem viram arte; saída: cartão de pronto), Notion, Jira, webhook e agente de IA (só sugere).
Chaves ficam em texto no autorip.json.

## Testes
`python tests/test_offline.py`, `tests/test_prints.py`, `tests/test_integrations.py`, `tests/test_agent.py`; formato PRT em autorip/prt.py.

## 0.6
- Card "Fila de impressão": lista os .PRT prontos na pasta de saída (mais antigo primeiro, com miniatura e medidas);
  "Impresso" move o arquivo para a pasta de impressos; a lixeira apaga (pede senha).
- Card "Registro" redesenhado (linhas com hora e etiqueta colorida, botão Copiar).
- O .PRT agora é gravado como .part e só ganha o nome final quando está completo.
