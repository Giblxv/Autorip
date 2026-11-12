# Consulta de estado com outbox grande

Base publicada `v0.8.22`. Exploração 3 pares, confirmação 5 pares, A/A 3 pares, nos casos ausente/0/32/2000/10000 avisos, 12 consultas seguidas após a primeira leitura separada. Uma bateria adicional de 3 pares usa 8 chamadas espaçadas em um segundo, com 10000 avisos e expiração real do cache. Cada lado/amostra usa um processo novo e servidor HTTP local real; os corpos de resposta são SHA-256 idênticos dentro de cada par. Nenhum aviso é enviado. A geração dos arquivos, imports e inicialização ficam fora do cronômetro.

O A/A varia bastante (inclusive razão 1,36 no caso grande); não se interpreta ganho pequeno como confirmado. A redução de decodificações é verificável por contagem, as baterias grandes e a cadência repetiram o ganho. O primeiro acesso ainda lê e valida a fila. O cache retém apenas contagem/assinatura/tempo, sem dados de trabalhos, e não disputa o lock de envio. Os testes cobrem invalidação, expiração, mudança durante leitura, concorrência, erros e privacidade.

Os JSONs preservam amostras e primeiras leituras, inclusive casos pequenos inconclusivos. `exploration-benchmark.py.txt` é a fonte inicial; `measured-benchmark.py.txt` acrescenta apenas suporte à cadência e seleção de casos. A mudança posterior só da versão do aplicativo não altera os algoritmos medidos. O log completo registra 1105 testes antes do teste adicional de caminho relativo; `counter-final-tests.log` cobre a revisão final desse contador. A revisão de publicação recebe a matriz completa.

Esta melhoria reinicia a contagem da nova campanha. As 25 hipóteses da versão anterior não se somam à sequência atual. O prazo permanece 22h de São Paulo de 11/11/2026.
