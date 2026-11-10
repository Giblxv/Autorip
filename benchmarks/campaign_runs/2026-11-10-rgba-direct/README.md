# Dados da investigação RGBA direto

- `report.json` e `confirmation.json`: duas baterias completas, 13 cenários e 29 PRTs por execução, 15 repetições, processos persistentes separados, afinidade 0–3.
- `wide.json`: larguras 5,08/10,16 cm, RGBA pequeno, pequeno sem ICC e pressão de oito perfis RGB/RGBA alternados. Quinze repetições; os três controles pequenos usam CPU 0, os largos usam 0–3.
- `small-confirmation.json`: segunda medição dos dois controles pequenos, 15 repetições, CPU 0.
- `aa-control.json`: mesmos dois controles e motores idênticos, comprovados por `source_sha256`; mede a variação que pode aparecer sem mudar código.
- `campaign.json`: 15 hipóteses consecutivas sem aceite, 23 cenários corretos e 14 cronometrados, cinco repetições; execução sem `--apply`.
- `verification.json`: auditoria independente dos 23 PRTs, da sequência de 15 recusas e dos módulos finais contra o checkout.
- `environment.json`: ambiente, hashes da implementação e resultado dos 757 testes locais.
- `exploration/`: resultados anteriores no mesmo processo (7, 15 e 15 repetições) e snapshots dos scripts usados. Esses dados são preservados, inclusive resultados desfavoráveis; não fundamentam uma promessa de velocidade.

Os intervalos de reamostragem dentro de um par de processos não incluem toda a
variação entre processos, como demonstra o controle A/A. Os tempos são indicativos.
A economia de RSS depende do tamanho de fonte/saída; nos controles largos o pico
ficou praticamente igual. Consulte a [análise completa](../../../docs/refinements/DIRECT-RGBA-ICC.md).

Os perfis sintéticos podem ter hashes diferentes entre baterias porque o Pillow
inclui a data de criação. Os hashes e metadados dos 29 PRTs coincidem entre as
duas baterias completas. O perfil CMYK externo é identificado por hash.
