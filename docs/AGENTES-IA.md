# Contas de IA

Abra **Configurações → Agentes de IA**, escolha um serviço e clique em **Adicionar conta**. Estão disponíveis Claude/Anthropic, ChatGPT/OpenAI, Gemini/Google, DeepSeek, Manus, Grok/xAI, Perplexity e OpenRouter. Informe a chave de API e confira o modelo ou perfil. Salvar uma conta não faz consultas externas.

Você pode cadastrar várias contas do mesmo provedor. O AutoRIP não impõe um teto de quantidade de chaves. A tela mostra 50 contas por página para manter a edição leve; as demais permanecem cadastradas. As cotas, os custos e os limites de cada provedor continuam valendo. Uma assinatura de chat não necessariamente inclui acesso à API: use uma chave emitida pelo serviço correspondente.

Cada conta pode ter nome, modelo e estado ativo/desativado. As chaves salvas nunca são devolvidas ao navegador: o campo fica vazio com a indicação de chave salva. Deixe-o vazio para manter a chave ou digite outra para substituir. Ao trocar o provedor de uma conta existente, informe uma nova chave. **Remover conta** exclui o cadastro quando você salva. A chave Anthropic anterior continua funcionando por compatibilidade.

No cartão **Agentes de IA**, escolha um provedor e clique em **Analisar melhorias**. As chaves ativas desse provedor se alternam entre consultas. **Automático** usa o primeiro provedor com uma conta ativa cadastrada; sem contas adicionais, usa a configuração Anthropic anterior. Não há repetição automática de uma consulta que falhou, evitando duplicar tarefas e cobranças. Para consultar serviços externos, desative **Modo offline** em **Rede**.

Manus cria uma tarefa privada e retorna seu endereço para acompanhamento na conta Manus. O resultado é assíncrono e não aparece como análise concluída no painel. A integração usa [task.create v2](https://open.manus.ai/docs/v2/task.create), com `x-manus-api-key`; o campo modelo corresponde a `agent_profile`, inicialmente `standard`. Os demais serviços retornam texto no painel; a disponibilidade de pesquisa na web depende do provedor e do modelo.

O contexto enviado contém parâmetros técnicos de impressão, estados dos últimos trabalhos e contagem de eventos. Não inclui chaves de outras contas, caminhos, nomes dos arquivos ou conteúdo dos registros. O agente sugere melhorias; não altera configurações. As chaves são salvas no arquivo de configuração local protegido pelo programa. Não compartilhe `autorip.json`.
