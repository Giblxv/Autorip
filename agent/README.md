# PrintExpAgent

Agente Windows para observar a pasta de saída do AutoRIP, controlar a fila de PRTs e operar o PrintExp via pywinauto.

## Segurança padrão

O agente começa com `auto_print: false` no `print-agent.json`. Nesse modo, ele calcula o hash e registra o PRT como `aguardando_autorizacao`, sem clicar em imprimir. Depois de inspecionar a interface real do PrintExp, altere `auto_print` para `true`.

Use `--dry-run` para testar a descoberta de arquivos sem abrir o PrintExp.

## Calibração

A primeira versão usa `Ctrl+O` para abrir e `Ctrl+P` para imprimir. Os textos de confirmação são configuráveis em `confirmation_regexes`. Como as versões do PrintExp podem ter idiomas, telas e controles diferentes, os seletores devem ser validados com Inspect.exe ou `print_control_identifiers()` antes de produção.

Um job que chega a `impressao_solicitada` e perde a confirmação fica em `revisao_manual`; o agente não reenvia automaticamente.

## Compilação

```bat
python -m pip install -r agent\requirements.txt pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --name PrintExpAgent --distpath dist\PrintExpAgent --workpath build\pyinstaller-agent --noconsole agent\print_agent.py
```
