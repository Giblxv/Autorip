# Integração visual Looney Psychedelic

O pacote `AutoRIP_0.8.27_Looney_Psychedelic_Pack.zip` foi analisado como
material de referência, sem executar seus scripts nem substituir o programa
pelas telas de demonstração. SHA-256 do ZIP recebido:
`d38de7fbf267f2c8a5393a81fb58a961d3cbe36d56d79e45e1c6e530fa9ebd46`.

## Elementos aplicados

- Paleta roxa escura, ciano, magenta e amarelo, com anéis e gota de tinta.
- Ícone e imagens do instalador recebidos no pacote. `brand-mark.png` é o PNG
  de 256 px já contido no ICO, extraído sem redesenhar ou alterar os pixels.
- CSS único para o painel real, incluindo filas, configuração, QR e prévia da
  folha. Os dados continuam vindo das APIs existentes e autenticadas.
- Cores e ícone da janela nativa, mantendo sua comunicação por fila na thread
  principal, a inicialização do servidor e o encerramento existentes.
- Tela de conexão Android e tema Flutter iOS, mantendo endereço, histórico,
  leitor QR e acesso ao painel real.

O layout funciona a partir de 320 px. Foco de teclado e contraste de texto são
visíveis no tema escuro. A entrada dura menos de um segundo e não intercepta
cliques. Somente barras de trabalhos em processamento têm animação contínua;
trabalhos aguardando ou concluídos ficam estáticos. A aba oculta pausa também
pseudo-elementos. A preferência de movimento reduzido desativa as animações.
Não há dependências adicionais, fontes externas, áudio automático ou novos
pollers. O empacotamento continua incluindo a pasta `autorip/ui`.

## Adaptações da demonstração

O painel do ZIP contém nomes de artes, níveis de tinta, aproveitamento e
indicadores de integridade fixos. Esses valores não foram transformados em
telemetria do programa. A lupa e as alternâncias de branco/retícula da
demonstração não representam os dados do RIP; a prévia mantida é o planejador
real com exportações SVG/JSON.

As APIs de eventos, upload e pareamento do pacote diferem das implementadas.
Foram mantidos os endpoints existentes, o token, a política de conteúdo, a
escrita segura de arquivos e o QR HTTP(S) compatível com os aplicativos.
Os módulos de tray, bootstrap e build do pacote não substituem o ciclo de vida
do programa. A barra de purga proposta em `roll_leader.py` altera a imagem
impressa e não faz parte desta atualização gráfica.

## Verificação

Na integração sobre a `main` de base `4925a3b`:

- `python -m pytest -q`: 1.210 testes aprovados.
- `node tools/smoke_queue_ui.cjs`: 100 trabalhos, foco, rolagem, pausa,
  retomada e cancelamento; sem transbordamento em 390/320 px.
- `node tools/smoke_polling_ui.cjs`: 45 cenários aprovados.
- `node tools/smoke_nesting_ui.cjs`: 9 cenários aprovados, com prévia e
  exportações reais e proteção contra respostas atrasadas.
- `node tools/smoke_visual_ui.cjs`: painel e diálogos em 1.440, 768, 390 e
  320 px; ativos carregados, movimento reduzido, pausa em segundo plano e
  formulário Android com validação e conexão preservadas. Salva capturas e
  `report.json` no diretório de saída informado como primeiro argumento.

Os smokes de navegador requerem Playwright/Chromium e aceitam as variáveis
`AUTORIP_PYTHON`, `AUTORIP_PLAYWRIGHT_MODULE`, `AUTORIP_CHROMIUM` e
`AUTORIP_NO_SANDBOX`. Usam apenas dados temporários. As verificações Flutter
e Windows também rodam pelos workflows existentes no pull request.

Esta integração não altera processamento de pixels, cor, formato PRT,
protocolo PrintExp ou versão de release.
