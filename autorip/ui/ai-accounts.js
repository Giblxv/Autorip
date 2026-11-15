// Contas sem teto de quantidade. Só uma página de campos fica no DOM por vez.
let aiAccounts=[],aiCatalog=[],aiPage=0,aiSequence=0;
const aiPageSize=50;
function clearAiDraft(){
 for(const account of aiAccounts)account.key="";
 aiAccounts=[];aiCatalog=[];aiPage=0;
 document.querySelectorAll('.ai-accounts input[type="password"]').forEach(input=>input.value="");
}
window.resetAiAccounts=()=>{clearAiDraft();setAiProviders([])};
$("dlg").addEventListener("close",clearAiDraft);
function setAiProviders(providers){
 const select=$("agentProvider"),previous=select.value;
 const signature=JSON.stringify(providers);
 if(select.dataset.signature===signature)return;
 select.dataset.signature=signature;select.replaceChildren(new Option("Automático", "auto"));
 for(const provider of providers)select.append(new Option(`${provider.name} (${provider.keys} chave${provider.keys===1?"":"s"})`,provider.id));
 if([...select.options].some(option=>option.value===previous))select.value=previous;
}
function collectAiAccounts(){
 return aiAccounts.map(account=>({...(account.id?{id:account.id}:{}),provider:account.provider,
  label:account.label,model:account.model,key:account.key,enabled:account.enabled}));
}
function renderAiAccounts(container,accounts,catalog){
 for(const account of aiAccounts)account.key="";
 aiCatalog=catalog;aiAccounts=accounts.map(account=>({...account,key:"",clientId:++aiSequence}));aiPage=0;
 container.className="full ai-accounts";
 const note=document.createElement("p");note.textContent="Adicione quantas contas precisar, inclusive várias do mesmo provedor. As chaves ativas do provedor escolhido se alternam a cada consulta. Cotas e custos de cada serviço continuam valendo. Nenhuma consulta é enviada ao salvar.";
 const controls=document.createElement("div");controls.className="row";
 const picker=document.createElement("select");picker.setAttribute("aria-label","Provedor da nova conta de IA");picker.id="aiNewProvider";
 for(const provider of catalog)picker.append(new Option(provider.name,provider.id));
 const add=document.createElement("button");add.type="button";add.className="c";add.id="aiAddAccount";add.textContent="Adicionar conta";
 const rows=document.createElement("div");rows.id="aiAccountRows";
 const pages=document.createElement("div");pages.className="row";
 const previous=document.createElement("button"),next=document.createElement("button"),count=document.createElement("span");
 previous.type=next.type="button";previous.textContent="Anteriores";next.textContent="Próximas";count.id="aiAccountCount";count.setAttribute("role","status");
 pages.append(previous,count,next);controls.append(picker,add);container.append(note,controls,rows,pages);
 function draw(){
  rows.replaceChildren();aiPage=Math.min(aiPage,Math.max(0,Math.ceil(aiAccounts.length/aiPageSize)-1));
  const start=aiPage*aiPageSize;
  for(const account of aiAccounts.slice(start,start+aiPageSize)){
   const row=document.createElement("fieldset");row.className="ai-account";row.dataset.accountId=account.id||"new";
   const legend=document.createElement("legend");legend.textContent=account.label||aiCatalog.find(provider=>provider.id===account.provider)?.name||account.provider;row.append(legend);
   const fields=document.createElement("div");fields.className="ai-fields";
   const providerLabel=document.createElement("label"),providerInput=document.createElement("select");providerLabel.textContent="Provedor";providerInput.className="ai-provider";
   for(const provider of aiCatalog)providerInput.append(new Option(provider.name,provider.id));providerInput.value=account.provider;
   providerInput.onchange=()=>{account.provider=providerInput.value;account.model=aiCatalog.find(provider=>provider.id===account.provider).model;modelInput.value=account.model;legend.textContent=account.label||providerInput.selectedOptions[0].textContent};providerLabel.append(providerInput);fields.append(providerLabel);
   function field(label,name,type="text"){
    const wrapper=document.createElement("label"),input=document.createElement("input");wrapper.textContent=label;input.type=type;input.className="ai-"+name;input.value=account[name];input.autocomplete=type==="password"?"new-password":"off";
    input.oninput=()=>{account[name]=input.value;if(name==="label")legend.textContent=account.label||providerInput.selectedOptions[0].textContent};wrapper.append(input);fields.append(wrapper);return input;
   }
   field("Nome da conta (opcional)","label");const modelInput=field("Modelo / perfil Manus","model");
   const keyInput=field("Chave de API","key","password");keyInput.placeholder=account.has_key?"Chave salva; deixe vazio para manter":"Cole a chave desta conta";keyInput.spellcheck=false;
   const enabledLabel=document.createElement("label"),enabled=document.createElement("input");enabled.type="checkbox";enabled.className="ai-enabled";enabled.checked=account.enabled;enabled.onchange=()=>account.enabled=enabled.checked;enabledLabel.append(enabled,document.createTextNode(" Conta ativa"));fields.append(enabledLabel);
   const remove=document.createElement("button");remove.type="button";remove.className="sm k ai-remove";remove.textContent="Remover conta";remove.onclick=()=>{account.key="";aiAccounts=aiAccounts.filter(item=>item!==account);draw()};fields.append(remove);row.append(fields);rows.append(row);
  }
  count.textContent=aiAccounts.length?`${start+1}–${Math.min(start+aiPageSize,aiAccounts.length)} de ${aiAccounts.length} contas`:"Nenhuma conta adicional";
  previous.disabled=aiPage===0;next.disabled=start+aiPageSize>=aiAccounts.length;
 }
 add.onclick=()=>{const provider=aiCatalog.find(item=>item.id===picker.value);aiAccounts.push({provider:provider.id,label:"",model:provider.model,key:"",enabled:true,has_key:false,clientId:++aiSequence});aiPage=Math.floor((aiAccounts.length-1)/aiPageSize);draw();rows.lastElementChild?.querySelector(".ai-key").focus()};
 previous.onclick=()=>{aiPage--;draw()};next.onclick=()=>{aiPage++;draw()};draw();
 const foot=document.createElement("p");foot.textContent="Manus cria uma tarefa privada e retorna o endereço para acompanhar o resultado. Os demais retornam a análise no painel; pesquisa na web depende do serviço. Desative o modo offline para consultar uma IA externa.";container.append(foot);
}
if(appliedState)setAiProviders(appliedState.ai_providers||[]);
