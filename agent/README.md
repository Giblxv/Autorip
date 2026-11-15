# PrintExpAgent

Agente Windows para observar a pasta de saída do AutoRIP, controlar a fila de PRTs e operar o PrintExp via pywinauto.

## Interface gráfica

O **PrintExpAgent 0.2.0** tem uma janela nativa com a identidade visual do AutoRIP: tema escuro, marca e destaques em ciano, magenta e amarelo. Abra **Agente PrintExp** no menu Iniciar ou execute:

[Prévia da interface](../docs/refinements/assets/printexp-agent-interface.png).

```powershell
.\PrintExpAgent.exe --gui
```

A janela mostra modo de operação, pastas, IPv4, últimos 200 trabalhos e registro de eventos. Em **Configurações**, escolha o executável do PrintExp e as pastas, ajuste os intervalos e salve. O banco de histórico existente e as opções avançadas do JSON são preservados.

**Testar conexão com PrintExp** pode abrir/focar o programa configurado, mas não carrega PRT nem solicita impressão. **Iniciar** acompanha a pasta e usa o modo salvo. O padrão continua seguro (`auto_print: false`): registra os arquivos e aguarda autorização. Para automatizar a impressão, primeiro calibre os controles reais e ative a opção na configuração.

**Parar** impede os próximos trabalhos e aguarda a operação atual terminar. A impressão física não é pausada. Fechar a janela também aguarda; se a conclusão não for confirmada, o trabalho permanece em revisão. Trabalhos em revisão ou com pedido de impressão pendente não são reenviados automaticamente.

Sem argumentos, o executável abre a janela e retoma o monitoramento quando já existe configuração, preservando o comportamento de inicialização anterior. `--gui` abre parado para configuração; `--gui --start` abre e inicia. Para execução sem janela, use:

```powershell
.\PrintExpAgent.exe --headless
.\PrintExpAgent.exe --dry-run --once
```

A interface funciona localmente, sem servidor HTTP ou novas portas de administração. A descoberta LAN existente continua disponível; ela anuncia o computador, mas não é um receptor TCP de PRTs.

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

## UIPI e privilégios do Windows

Por padrão, `uipi_guard` fica ligado. Antes de focar a janela, o agente compara o nível de integridade do próprio processo com o nível do processo do PrintExp. Se o PrintExp estiver elevado e o agente estiver em nível comum, a automação é interrompida com uma mensagem explicando que ambos devem rodar no mesmo nível de privilégio ou que deve ser instalado um helper elevado revisado. O agente não tenta contornar o UIPI com cliques forçados.

Se o Windows não permitir ler um dos tokens de integridade, a guarda também bloqueia a automação (fail closed), evitando interpretar uma falha de diagnóstico como autorização para controlar a interface.

Para diagnóstico controlado, `uipi_guard: false` desativa essa checagem, mas isso não concede permissões e pode continuar impedindo a automação. Não use essa opção em produção sem validar o comportamento da instalação.

## Calibração

A primeira versão usa `Ctrl+O` para abrir e `Ctrl+P` para imprimir. Os textos de confirmação são configuráveis em `confirmation_regexes`. Como as versões do PrintExp podem ter idiomas, telas e controles diferentes, os seletores devem ser validados com Inspect.exe ou `print_control_identifiers()` antes de produção.

Um job que chega a `impressao_solicitada` e perde a confirmação fica em `revisao_manual`; o agente não reenvia automaticamente.

## Compilação

```bat
python -m pip install -r agent\requirements.txt pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --name PrintExpAgent --paths . --distpath dist\PrintExpAgent --workpath build\pyinstaller-agent --noconsole --icon installer_assets\autorip.ico --add-data "autorip\ui\brand-mark.png;autorip\ui" agent\print_agent.py
```
