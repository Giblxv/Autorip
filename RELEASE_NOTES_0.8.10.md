# AutoRIP v0.8.10

Esta versão adiciona adaptação automática de desempenho baseada no hardware do computador onde o AutoRIP é instalado.

Durante a instalação Windows, o instalador executa `tools\\detect_hardware.ps1`. O script identifica processador, núcleos, threads, memória RAM, discos e GPU e grava o resultado em `%APPDATA%\\AutoRIP\\hardware_profile.json`.

O motor utiliza esse perfil para escolher automaticamente o tamanho das tiras de processamento e o limite seguro dos buffers temporários. Em computadores com pelo menos 24 GiB de RAM e 6 núcleos, como um Ryzen 5 5500 com 32 GiB, o perfil alto usa tiras de até 1024 linhas e até 1 GiB de buffers, reduzindo o overhead de processamento. Computadores menores usam perfis equilibrado ou conservador.

A detecção interna continua como fallback quando o programa é executado fora do instalador ou quando o arquivo de perfil não está disponível.

Validação: 191 testes passando, compilação Python, Ruff, Bash e sintaxe do instalador verificadas.
