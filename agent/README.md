# PrintExpAgent

Agente Windows para observar a pasta de saída do AutoRIP, controlar a fila de PRTs e operar o PrintExp via pywinauto.

## Descoberta do computador receptor

O agente anuncia seus IPv4 na rede local para a configuração do AutoRIP. Há um
modo dedicado que não observa arquivos nem imprime:

```powershell
.\PrintExpAgent.exe --network-discovery --print-port 9100
```

Veja [descoberta IPv4 e configuração em dois computadores](../docs/PRINTEXP-DESCOBERTA-IPV4.md).
O anúncio também fica ativo na execução normal; `network_discovery: false`
desativa-o. A porta anunciada pode ser configurada por `printexp_port`.
O agente 0.1.1 acompanha mudanças de IPv4/interface, retoma o anúncio após
reconexão e tenta novamente quando a rede ainda não está disponível ao iniciar.

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
