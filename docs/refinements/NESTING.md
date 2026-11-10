# Planejamento de folha no painel

Integra o `nesting.py` fornecido pelo usuário ao modelo `LayoutItem` e ao painel
do AutoRIP. O algoritmo fica em `autorip/sheet_nesting.py`; `autorip/nesting.py`
expõe a API nova e preserva o encaixe anterior com rectpack.

## Operação

1. Salve as imagens na hot folder e faça login no painel.
2. Abra **Hot folder → Planejar folha** e selecione as artes.
3. Defina quantidade e largura em centímetros. Largura em branco usa a medida
   física da fonte, limitada à largura útil; a altura permanece proporcional.
4. Ajuste folha, margem, espaçamento e permissão de rotação de 90°.
5. Use **Calcular encaixe** para ver a folha, seu comprimento e aproveitamento.
6. Exporte a prévia SVG e o planejamento JSON quando necessário.

A largura máxima é 58 cm. O comprimento é calculado a partir das peças. Há até
100 peças por planejamento, incluindo cópias. O servidor aceita um cálculo por
vez e responde HTTP 429 se outro estiver em andamento. Nenhum cálculo ou consulta
adicional fica rodando em segundo plano quando o planejador está fechado.

O cálculo lê somente os cabeçalhos das imagens selecionadas. As fontes continuam
na hot folder e a fila de RIP permanece intacta, inclusive se estiver cheia.
Se uma arte sair da pasta ou mudar durante a leitura, o painel pede atualização.
O plano é uma fotografia das medidas lidas; não acompanha alterações posteriores
nos arquivos. A composição e impressão de uma folha PRT não fazem parte desta etapa.

O SVG mostra caixas e nomes, sem incorporar os bitmaps. As posições estão em
centímetros e o JSON conserva largura/altura da peça e sua rotação separadamente.
Para 90°/270°, a caixa ocupada troca largura e altura. A rotação do plano é
adicional à orientação EXIF considerada nas dimensões da fonte. Caminhos locais
não entram na resposta ou nos arquivos exportados.

## Algoritmo e correções da integração

Testa cinco ordens e três heurísticas MaxRects: bottom-left, melhor lado curto e
melhor área residual. Com rotação permitida, avalia também as versões com rotação,
totalizando até 30 tentativas. O encaixe por faixas entra como referência; somente
um candidato mais curto, dentro da largura útil e sem sobreposição é aceito.
O espaçamento é reservado em torno das caixas e a saída volta à ordem de entrada.
Não é uma prova de ótimo global.

Correções em relação ao arquivo recebido:

- Peças que excedem a largura e cabem giradas são orientadas antes da validação;
  sem permissão de rotação continuam sendo recusadas.
- Parâmetros, dimensões, posições e rotações são validados; NaN, infinito e ângulos
  fracionários não passam pela verificação geométrica.
- O aproveitamento divide as dimensões antes de multiplicar, evitando `inf/inf`
  com medidas grandes e finitas. A altura acumulada também é verificada.
- O backend confina a leitura à hot folder, recusa links e valida quantidades
  antes do acesso aos arquivos. A leitura não decodifica os rasters completos.
- O painel invalida o plano após editar opções, fecha e limpa dados ao trocar de
  sessão, descarta respostas antigas e libera as URLs de prévia descartadas.

As posições são arredondadas para seis casas decimais, com tolerância geométrica
de `1e-6` cm, seguindo o modelo existente. Itens e resultados são independentes;
o algoritmo não altera a lista original. Não há dependência nova de produção,
acesso externo ou alteração dos módulos engine/prt/morph.

Em uma prova simples, peças de 6 × 6, 4 × 4 e 4 × 2 cm em folha de 10 cm, sem
margem/gap, usam **6 cm de comprimento**, contra 8 cm das faixas. Isso descreve
essa geometria; o resultado depende das peças selecionadas.

## Biblioteca e API HTTP

```python
from autorip.layout import LayoutItem, sheet_height
from autorip.nesting import nest_layout, check_layout, utilization

items = [LayoutItem("a", "arte.png", "", 600, 400, 12, 8)]
packed = nest_layout(items, sheet_width_cm=58, margin_cm=.2,
                     gap_cm=.2, allow_rotation=True)
assert check_layout(packed)
print(sheet_height(packed), utilization(packed))
```

`nest(LayoutItem, ...)` encaminha para esse algoritmo; tuplas da API anterior
continuam encaminhadas para `nest_sheets(items, sheet_w_cm, sheet_h_cm, ...)`,
retornando `Placements` com `unplaced`. Prefira `nest_layout`/`nest_sheets` quando
a coleção vazia e argumentos posicionais tornarem a escolha ambígua. Somente a
API anterior requer rectpack; o planejador funciona sem ele.

`POST /api/layout/plan` usa a mesma autenticação `X-Token`, origem e restrição de
host do painel. Aceita JSON de até 64 KiB:

```json
{
  "sheet_width_cm": 58,
  "margin_cm": 0.2,
  "gap_cm": 0.2,
  "allow_rotation": true,
  "items": [{"name": "arte.png", "width_cm": 12, "quantity": 3}]
}
```

Retorna `items`, `sheet_width_cm`, `sheet_height_cm`, `margin_cm`, `gap_cm`,
`utilization` (fração de 0 a 1) e `svg`. Só aceita nomes de imagens da hot folder;
`width_cm` pode ser omitido. Quantidade é um inteiro positivo e o total é limitado
a 100. Não cria jobs, arquivos temporários de arte ou saídas PRT.

## Verificação

```bash
python -m pytest -q
node tools/smoke_nesting_ui.cjs /tmp/nesting-browser
```

O smoke de navegador usa Playwright/Chromium e um backend temporário. As variáveis
`AUTORIP_PYTHON`, `AUTORIP_CHROMIUM`, `AUTORIP_PLAYWRIGHT_MODULE` e
`AUTORIP_NO_SANDBOX` têm o mesmo significado dos outros smokes de UI.

Os cenários incluem prévia e downloads reais, edição/fechamento/troca de sessão
com resposta pendente, limite de cópias, fonte ausente, login e telas de 390/320 px.
As provas geométricas cobrem entradas aleatórias determinísticas, rotações,
espaçamento/margens, medidas não finitas, ausência de rectpack e API antiga.
O smoke do executável também calcula duas peças, confere preservação da fonte
e verifica que o JavaScript do planejador entrou no pacote Windows.

Nesta integração, **709 testes locais passaram em 60,58 s**, incluindo 50 novos
de geometria/API. Os nove cenários do planejador e as regressões de fila,
miniaturas e 23 cenários de consultas passaram sem erros JavaScript.
[Resultados, hashes e validação local](nesting-validation.json). O motor mantém
a campanha anterior de 15 rodadas sem novo ganho, sem repetir rodadas idênticas
por uma alteração de planejamento/interface.
