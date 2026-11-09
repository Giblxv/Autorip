# AutoRIP v0.8.11

Esta versão adiciona manutenção automática ao servidor Ubuntu.

- O instalador habilita `autorip-maintenance.timer` diariamente às 03:00 no horário local.
- O serviço para o worker do AutoRIP antes da manutenção.
- O sistema executa `systemd-tmpfiles --clean` e remove apenas temporários antigos em `/tmp` e `/var/tmp`.
- As pastas `/srv/autorip`, incluindo a hot folder e a saída PRT, nunca são tocadas pelo script.
- O computador é reiniciado ao final para liberar memória e encerrar processos antigos.
- Há um modo de teste com `AUTORIP_MAINTENANCE_NO_REBOOT=1`.

Validação: 191 testes passando, sintaxe Bash validada, unidades systemd verificadas e pacote USB conferido.
