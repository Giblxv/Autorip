# Campanha de desempenho com prazo em 13/11/2026

Base: v0.8.25. Prazo: 13/11 às 22h de São Paulo (14/11 às 01h UTC), ou 100 rodadas consecutivas sem melhoria confirmada. Cada aceite zera a sequência. A contagem desta campanha começa em zero. A campanha anterior terminou e sua contagem não é reaproveitada.

O preflight excluiu 284 pares de fontes e 230 pares semânticos históricos; encontrou 157 propostas novas aplicáveis, sendo 151 planos de escalonamento e seis estratégias de meio-tom CMYK em lote. Não são contados planos equivalentes, aliases, caminhos inertes, erros ou rodadas parciais. Testes instrumentados comprovam que as seis estratégias executam planos diferentes. A guarda do carregamento também preserva hooks de meio-tom personalizados.

Passaram 1147 testes completos antes dos seis testes adicionais de ativação; os 19 testes focados de lotes, igualdade de planos e hooks passaram. Oito testes offline das barreiras de publicação passaram. Isso valida a preparação; não constitui prova de ganho de velocidade.

Cada candidata passa por limites numéricos e 30 PRTs idênticos. As 12 cargas cronometradas usam 15 pares, confirmação e controle A/A; aceites exigem regressões completas, controles ICC de cor plana/uma CPU e guarda contra a base inicial. O código e entradas são congelados; alterações externas suspendem a campanha preservando o trabalho. Medições não concorrem com outras suítes locais.

A execução é limitada e depende do ambiente permanecer ativo. Após o critério, uma auditoria independente e a matriz Linux/Windows validam o commit final antes de merge. Uma nova release só é preparada se uma melhoria de produção for aceita; pesquisa sem ganho preserva a versão existente. Nenhum ICC proprietário é distribuído. Relatórios finais serão adicionados ao término.

Uma pausa técnica antes de concluir a primeira rodada permitiu aprimorar a busca: as seis estratégias podem ser comparadas novamente após um aceite, preservando outras melhorias independentes. Os 36 pares de transições foram verificados; reaplicar a estratégia atual é inerte. Passaram 20 testes focados. Os hashes das seis propostas iniciais continuam idênticos ao preflight. A rodada parcial e suas fontes são preservadas em `maintenance/`, sem entrar na contagem.
