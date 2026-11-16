# Pesquisa: qualidade gráfica e acessibilidade da interface

## Objetivo

Melhorar a nitidez, legibilidade, consistência e percepção de qualidade do painel AutoRIP e das telas de conexão móvel sem trocar o estilo visual existente por uma reescrita genérica.

## O que foi verificado

**Fato verificável:** o painel usa `autorip/ui/looney.css`, tem layout responsivo para telas menores, estados de foco visível no cliente Android e suporte a `prefers-reduced-motion` no painel e na tela de conexão móvel.

**Fato verificável:** a interface já usa texto além de cor em vários estados: etiquetas de status, texto de progresso, ícones, mensagens e atributos ARIA. Isso reduz, mas não elimina, o risco de depender apenas de cor.

**Fato verificável:** o cliente iOS é Flutter e abre o painel em `WKWebView`; por isso, a qualidade visual deve ser verificada tanto na tela nativa de conexão quanto no painel web carregado.

## Ideias priorizadas

### 1. Tornar contraste e estados de interação mensuráveis

**Por que funciona para o público:** textos, botões e estados de fila continuam legíveis em telas pequenas, ambientes claros e para pessoas com baixa visão ou deficiência de visão de cores.

**Fato verificável:** as Human Interface Guidelines da Apple recomendam contraste suficiente, suporte a texto maior, não depender somente de cor e testar aparências clara e escura. Como referência WCAG AA, a página cita 4,5:1 para texto até 17 pt e 3:1 para texto maior ou negrito. [1]

**Hipótese:** a paleta atual pode conter combinações aceitáveis em alguns componentes e insuficientes em outros, especialmente texto secundário sobre superfícies escuras e estados de erro/aviso. Não foi executada uma auditoria de contraste completa; portanto, não há um número global a declarar.

**Proposta de validação:** criar um inventário de pares de cor efetivamente usados em texto, ícones e controles. Testar contraste em estados normal, hover, foco, desabilitado, erro, aviso e sucesso, nos dois temas se houver suporte. Corrigir tokens centralizados, não valores isolados, e repetir o smoke visual.

### 2. Melhorar hierarquia tipográfica e leitura em telas estreitas

**Por que funciona para o público:** ajuda o usuário a distinguir ação principal, estado do trabalho e informação secundária sem aumentar a densidade visual nem exigir zoom.

**Fato verificável:** o painel e o cliente móvel usam tamanhos responsivos, `overflow-wrap`, grids que viram uma coluna e controles com áreas de toque mínimas em vários componentes.

**Hipótese:** nomes de arquivos longos, mensagens de erro e caminhos de pasta ainda podem dominar visualmente cartões e diálogos, sobretudo em 320–390 px de largura.

**Proposta de validação:** testar conteúdo realista com nomes longos, mensagens extensas, aumento de fonte e orientação estreita. Preservar truncamento com acesso ao texto completo, manter foco visível e evitar que botões importantes saiam da área de toque. A aceitação deve cobrir 320, 390, 768 e desktop largo.

### 3. Reduzir movimento decorativo sem perder feedback de estado

**Por que funciona para o público:** mantém a sensação de atividade durante um RIP, mas evita distração, desconforto e custo de pintura contínua quando a animação não transmite informação nova.

**Fato verificável:** o painel tem uma animação de entrada e fluxo animado na barra de progresso, além de uma regra `prefers-reduced-motion` que desativa animações e transições.

**Hipótese:** o fluxo contínuo da barra pode ser substituído por um indicador mais econômico, como mudança discreta de cor/posição em atualizações reais, sem reduzir a compreensão do status.

**Proposta de validação:** comparar o estado processando, pausado, pronto e erro com movimento normal e reduzido. Medir repaints e verificar se o percentual, o texto e o estado continuam claros quando a animação é desligada. Não remover animações antes de cobrir os quatro estados.

### 4. Melhorar prévias sem sacrificar nitidez nem memória

**Por que funciona para o público:** uma miniatura nítida e estável ajuda a confirmar rapidamente se a arte correta foi enviada, especialmente em uma fila com nomes parecidos.

**Fato verificável:** o painel reaproveita miniaturas e possui cache limitado; a documentação do progresso registra que a imagem e a URL são preservadas durante atualizações de progresso.

**Hipótese:** qualidade percebida pode melhorar com dimensões e `object-fit` ajustados ao conteúdo, mas aumentar resolução ou cache indiscriminadamente pode elevar memória e decodificação.

**Proposta de validação:** comparar miniaturas transparentes, opacas, muito largas e muito altas em DPR 1, 2 e 3. Verificar nitidez, proporção, fundo de transparência, memória e troca correta quando a prévia muda. Não alterar pixels da arte de entrada ou do PRT.

### 5. Usar estados semânticos e acessibilidade como parte da qualidade gráfica

**Por que funciona para o público:** uma aparência “boa” continua útil quando a pessoa usa teclado, VoiceOver/TalkBack, contraste aumentado ou texto ampliado.

**Fato verificável:** a Apple recomenda suporte a texto maior, descrições para VoiceOver e indicadores além de cor. [1] O HTML atual já contém regiões `aria-live`, rótulos para controles e textos alternativos para miniaturas e QR codes.

**Hipótese:** ainda pode haver lacunas em diálogos, foco após atualização de listas, leitura de progresso e controles gerados dinamicamente. O código sugere cuidado com foco, mas isso precisa ser verificado em leitor de tela real.

**Proposta de validação:** cobrir teclado, foco após polling, leitor de tela, aumento de fonte e contraste aumentado. Toda mudança visual deve preservar nome acessível, estado, valor e ação do controle.

## Ordem recomendada

1. Auditoria de contraste e tokens de cor.
2. Teste de tipografia, nomes longos, foco e telas estreitas.
3. Auditoria de movimento e modo reduzido.
4. Matriz de miniaturas por proporção e densidade de pixels.
5. Teste em TalkBack e VoiceOver antes de alterar componentes gerados.

A ideia mais promissora é a auditoria combinada de contraste, tipografia e estados de foco. Ela melhora a qualidade percebida imediatamente, é independente do motor RIP e reduz risco de regressão antes de qualquer redesign. Não há base para afirmar que a paleta atual falha globalmente sem a medição componente a componente.

## Revisão crítica

### Problemas encontrados

- “Qualidade gráfica” não deve significar apenas mais efeitos, sombras ou animações; isso pode reduzir legibilidade e desempenho.
- Não é correto afirmar que todos os contrastes atuais atendem WCAG sem uma auditoria dos pares realmente renderizados.
- Não há evidência de que aumentar miniaturas ou trocar a paleta produz um ganho universal em todos os telefones.
- O painel e os clientes móveis não têm exatamente o mesmo caminho nativo; um teste visual em desktop não substitui TalkBack, VoiceOver e aparelhos físicos.
- Uma promessa de “interface premium” é vaga se não estiver ligada a critérios observáveis, como contraste, foco, tipografia, estabilidade da rolagem e nitidez.

### Versão final corrigida, pronta para uso

A melhoria gráfica deve priorizar legibilidade, hierarquia e consistência. O primeiro passo é auditar os tokens de cor e os pares usados por texto, ícones e estados de fila em normal, foco, aviso, erro, sucesso, modo escuro e contraste aumentado. A validação deve seguir uma referência objetiva de contraste e registrar as combinações que forem corrigidas.

Em seguida, a interface deve ser testada com nomes de arquivos longos, mensagens extensas, fontes ampliadas e larguras de 320 a desktop. A fila precisa manter foco, seleção, proporção das miniaturas e leitura dos estados depois de cada atualização. Texto e ícones devem continuar transmitindo o estado sem depender apenas de cor.

As animações devem permanecer somente quando comunicarem atividade ou mudança de estado. O modo `prefers-reduced-motion` deve continuar sendo respeitado, e a retirada ou simplificação de uma animação precisa ser acompanhada por feedback textual ou visual equivalente. Para Android e iOS, a aprovação final exige teste do painel no WebView correspondente e teste da tela nativa com os recursos de acessibilidade do sistema.

## Referências

[1]: https://developer.apple.com/design/human-interface-guidelines/accessibility "Accessibility — Apple Human Interface Guidelines"
[2]: https://github.com/Giblxv/Autorip "AutoRIP — repositório e documentação do projeto"
