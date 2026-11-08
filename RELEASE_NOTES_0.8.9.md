# AutoRIP v0.8.9

Esta versão corrige a geração do instalador Windows pelo Inno Setup.

A seção `[Files]` agora referencia explicitamente `dist\\AutoRIP\\AutoRIP.exe` em vez de usar um wildcard relativo. Isso evita o erro `Unknown filename prefix "dist\\AutoRIP\\C:"` em ambientes Windows onde o compilador resolve o caminho de origem de forma incorreta.

Também foram sincronizadas a versão do aplicativo, do instalador e do README para `0.8.9`.

A correção mantém o comportamento do aplicativo e inclui as funcionalidades da versão 0.8.8: servidor Linux, Samba, XRDP, Cockpit, Firefox, integração Trello com múltiplas listas, filtros de anexos e scanner persistente.
