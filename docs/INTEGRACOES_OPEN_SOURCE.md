# Candidatos open source para o AutoRIP

Pesquisa realizada em 2026-11-08 para avaliar editor offline, vetorização e processamento de imagens grandes.

## Recomendação

A combinação mais segura para o AutoRIP é manter o motor DTF Python como núcleo e integrar componentes opcionais por etapas:

1. **libvips/pyvips** para leitura, redimensionamento, preview e processamento de artes grandes por pipelines e regiões parciais.
2. **VTracer** para vetorização raster→SVG offline, principalmente logos, ilustrações e artes com poucas cores.
3. **Inkscape** como editor vetorial offline e ferramenta CLI para edição, limpeza e exportação SVG.
4. **Krita** como editor raster opcional para artes que exigem camadas, pintura e ajustes manuais.
5. **Potrace** apenas para traçados binários/monocromáticos, depois de revisar a obrigação GPLv2.
6. **SVG-Edit** somente se a interface web local continuar sendo usada; não é uma biblioteca Python nem um motor de vetorização.

Nenhum desses projetos substitui as regras DTF específicas do AutoRIP: separação CMYK/branco, choke, limite de tinta, retícula, ICC, canais, espelhamento, composição PRT e validação física.

## Inkscape

Repositório: <https://github.com/inkscape/inkscape>.

É um editor vetorial completo com SVG como formato principal, Trace Bitmap, edição visual, exportação e CLI. A integração recomendada é por subprocesso fixando uma versão, usando exportação e actions; uma extensão Inkscape em Python também é possível. É adequado para editar/limpar SVG e preparar artes, mas não é um RIP DTF.

Licença: GPL-2.0. Distribuir o programa ou uma obra derivada exige observar as obrigações copyleft e disponibilização de código conforme a licença. Arquivos criados pelo usuário não são automaticamente GPL.

Limitações: rastreamento colorido pode produzir muitos objetos; bitmaps e SVGs complexos consomem RAM/CPU; a CLI e actions mudam entre versões. Não oferece underbase branca, trapping DTF, halftone específico ou controle universal de impressora.

Fontes: <https://github.com/inkscape/inkscape>, <https://inkscape.org/about/license/>, <https://inkscape.org/doc/inkscape-man.html>, <https://wiki.inkscape.org/wiki/Using_the_Command_Line>, <https://inkscape.org/develop/extensions/>, <https://inkscape-manuals.readthedocs.io/en/latest/tracing-an-image.html>.

## Krita

Repositório: <https://github.com/KDE/krita>. O desenvolvimento principal também está no KDE Invent: <https://invent.kde.org/graphics/krita>.

É um editor raster completo com camadas, máscaras, filtros, texto, suporte a SVG limitado, ICC e plugins Python/PyQt. É adequado como editor externo ou integração opcional, mas pesado para embutir dentro do AutoRIP.

Licença: GPL-3.0 para a aplicação, com componentes de terceiros que devem ser verificados separadamente.

Limitações: não é um motor de vetorização automática nem RIP DTF; imagens grandes podem usar muita RAM e swap; a API Python é plugin dentro do processo do Krita, não uma biblioteca Python independente.

Fontes: <https://krita.org/en/about/license/>, <https://docs.krita.org/en/user_manual/python_scripting.html>, <https://docs.krita.org/en/user_manual/vector_graphics.html>, <https://docs.krita.org/en/reference_manual/preferences/performance_settings.html>.

## SVG-Edit

Repositório: <https://github.com/SVG-Edit/svgedit>.

É um editor SVG em JavaScript, com pacote reutilizável `@svgedit/svgcanvas`, eventos e handlers de abrir/salvar/exportar. Pode funcionar offline empacotado numa WebView ou navegador local.

Licença principal: MIT, com dependências que possuem licenças adicionais; os avisos precisam ser mantidos.

Limitações: não é biblioteca Python, não vetoriza raster e não é RIP. SVGs com bitmaps grandes dependem da memória do DOM/canvas. Para o AutoRIP, seria uma integração de interface, não a solução para imagens gigantes.

Fontes: <https://github.com/SVG-Edit/svgedit>, <https://github.com/SVG-Edit/svgedit/blob/master/LICENSE-MIT.txt>, <https://github.com/SVG-Edit/svgedit/blob/master/docs/tutorials/ExtensionDocs.md>, <https://github.com/SVG-Edit/svgedit/blob/master/docs/tutorials/Events.md>.

## VTracer

Repositório: <https://github.com/visioncortex/vtracer>.

Conversor raster→SVG em Rust, com CLI, biblioteca, WebAssembly e binding Python. A API Python oferece conversão por arquivo, bytes e pixels e permite presets, paleta, quantidade máxima de cores, remoção de speckles e simplificação de curvas. É o melhor candidato para a primeira integração de vetorização local.

Licença: MIT ou Apache-2.0 no binding, conforme a versão distribuída; confirmar os avisos da wheel escolhida.

Limitações: não é editor com camadas/nós e não oferece o pipeline DTF; fotos/arquivos grandes podem gerar SVG enorme e consumir RAM. A versão da wheel deve ser fixada porque PyPI e o repositório podem estar em versões diferentes.

Fontes: <https://github.com/visioncortex/vtracer>, <https://github.com/visioncortex/vtracer/blob/master/LICENSE>, <https://pypi.org/project/vtracer/>, <https://www.visioncortex.org/vtracer-docs/>.

## Potrace

Projeto oficial: <https://potrace.sourceforge.net/>. O GitHub encontrado é um espelho: <https://github.com/skyrpex/potrace>.

É excelente para bitmap binário, logos, lettering e silhuetas; tem CLI, `mkbitmap` e `libpotrace`. Para cores, cada máscara precisa ser separada antes e composta depois.

Licença: GPLv2 no projeto oficial; existe opção comercial não-GPL informada pelo próprio projeto. A licença deve ser revisada antes de redistribuir o componente no instalador.

Limitações: não trabalha diretamente com cor complexa, fotos, transparência ou centerline tracing; não é editor e não oferece streaming/tiling moderno. Não é a escolha padrão para o AutoRIP comercial sem resolver a licença.

Fontes: <https://potrace.sourceforge.net/>, <https://potrace.sourceforge.net/potrace.1.html>, <https://potrace.sourceforge.net/mkbitmap.1.html>, <https://potrace.sourceforge.net/faq.html>, <https://potrace.sourceforge.net/potracelib.pdf>.

## libvips/pyvips

Repositório: <https://github.com/libvips/libvips>. Binding Python: <https://github.com/libvips/pyvips>.

Biblioteca raster orientada a pipelines, avaliação sob demanda, regiões parciais, streaming e multithreading. É o candidato mais importante para substituir operações que hoje materializam a imagem inteira no Pillow. Pode carregar, redimensionar, recortar, rotacionar, compor, converter cores e gerar previews com consumo de memória mais controlado.

Licença: LGPL-2.1-or-later para libvips; bindings, codecs e loaders opcionais devem ser revisados individualmente.

Limitações: o streaming depende do formato e da operação; alguns codecs ainda precisam descomprimir para RAM ou arquivo temporário. Não é editor GUI, não vetoriza e não faz RIP DTF. Para distribuição Windows, os binários e loaders precisam ser empacotados/testados offline.

Fontes: <https://www.libvips.org/>, <https://www.libvips.org/API/8.17/how-it-works.html>, <https://www.libvips.org/API/8.17/how-it-opens-files.html>, <https://libvips.github.io/pyvips/intro.html>.
