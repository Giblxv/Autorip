# AutoRIP v0.8.13

Esta versão reforça o assistente de preparação de mídia e o pipeline de qualidade.

O `AutoRIP_Ubuntu_Media_Wizard.exe` agora baixa artefatos em arquivos `.part`, valida limites de tamanho, verifica espaço livre, executa `fsync` e só publica o destino após uma troca atômica. O bundle Linux é comparado ao SHA-256 exato do manifesto da release antes de ser aceito. No Windows, o Rufus só é aberto quando a assinatura Authenticode está válida e identifica o fornecedor esperado.

Foram adicionados testes de checksum e rollback de download. O CI passou a instalar Ruff, executar lint Python em Windows e Ubuntu e validar a sintaxe dos scripts Bash em um job separado.

O instalador Linux agora valida o CIDR informado antes de instalar XRDP/Cockpit e restringe o SMB somente a essa sub-rede, em vez de abrir todas as redes privadas. O serviço systemd recebeu isolamento adicional de kernel, cgroups, módulos, SUID/SGID, realtime e arquitetura de syscalls.

As URLs de artefatos do wizard agora exigem HTTPS sem credenciais embutidas, os manifests têm limite de leitura e a execução do PowerShell usa o caminho do sistema no Windows. Usuários configuráveis do serviço Linux são validados e `root` é recusado.

Validação local: 196 testes passando, Ruff, compilação Python, Bash e verificação de diferenças sem erros. A impressão física e a assinatura do Rufus não são simuladas pelo ambiente Linux; a verificação Authenticode ocorre no executável Windows.
