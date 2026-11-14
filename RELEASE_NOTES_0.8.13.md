# AutoRIP v0.8.13

Esta versão reforça o assistente de preparação de mídia e o pipeline de qualidade.

O `AutoRIP_Ubuntu_Media_Wizard.exe` agora baixa artefatos em arquivos `.part`, valida limites de tamanho, verifica espaço livre, executa `fsync` e só publica o destino após uma troca atômica. O bundle Linux é comparado ao SHA-256 exato do manifesto da release antes de ser aceito. No Windows, o Rufus só é aberto quando a assinatura Authenticode está válida e identifica o fornecedor esperado.

Foram adicionados testes de checksum e rollback de download. O CI passou a instalar Ruff, executar lint Python em Windows e Ubuntu e validar a sintaxe dos scripts Bash em um job separado.

Validação local: 194 testes passando, Ruff, compilação Python, Bash e verificação de diferenças sem erros. A impressão física e a assinatura do Rufus não são simuladas pelo ambiente Linux; a verificação Authenticode ocorre no executável Windows.
