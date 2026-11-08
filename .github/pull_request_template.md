> Este checklist é orientativo: ele não bloqueia merges por si só. Configure rulesets/branch protection e required reviews no GitHub para aplicar enforcement; use “N/A” acompanhado de justificativa quando um item não se aplicar.

## Qual problema foi identificado?
Descreva o defeito, a reprodução e a evidência. Evite declarar que algo foi testado se não foi.

## O que esta alteração faz?
Descreva os arquivos, o comportamento anterior e o novo comportamento. Explique como reverter se houver regressão.

## Impacto no motor RIP e na produção DTF
- [ ] Não altera o formato PRT, ordenação de canais, DPI, espelhamento, ICC ou branco.
- [ ] Altera a geração PRT ou a cor: documentei exatamente a diferença e anexei resultados sintéticos.
- [ ] Pode afetar instalação, atualização, pastas de entrada/saída ou arquivos existentes: documentei o risco.

**Notas sobre equipamento:** PRT deste projeto é formato inferido, não uma especificação oficial. Se houver mudança de parâmetros de impressão, documente o teste com PrintExp/Hoson e o resultado; sem esse teste, informe "não validado fisicamente".

## Testes e evidências
- [ ] Testes relevantes adicionados/atualizados.
- [ ] `python -m pytest -q` passou localmente ou no GitHub Actions (informe onde).
- [ ] Windows foi validado, quando afetado (informe runner ou máquina).
- [ ] Não houve verificação física de impressão (deixe marcado se aplicável).

Resultado, comandos e links de execução:

## Segurança, dados e rollback
Descreva efeitos de rede, permissões, credenciais, compatibilidade de configuração e rollback.

## Revisão e aprovação
- [ ] Branch separada da `main`.
- [ ] Código não foi enviado diretamente para `main`.
- [ ] Sem merge automático: aguarda aprovação explícita do responsável.
