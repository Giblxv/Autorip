/* Network setup only: discovery and TCP reachability never transmit a PRT. */
function renderPrintExpNetwork(grid, requestVersion) {
 const box=document.createElement('div');box.className='full';box.id='printexpNetwork';
 const local=document.createElement('p'),message=document.createElement('p'),results=document.createElement('div');
 local.textContent='Identificando os IPv4 deste computador…';message.setAttribute('role','status');message.setAttribute('aria-live','polite');
 const help=document.createElement('p');help.textContent='No computador do PrintExp, mantenha o agente AutoRIP em execução para descoberta local. Você também pode informar o IPv4 manualmente. Esta configuração ainda não envia arquivos para impressão.';
 const discover=document.createElement('button'),check=document.createElement('button');
 discover.type=check.type='button';discover.textContent='Buscar PrintExp na rede';discover.id='discoverPrintExp';check.textContent='Verificar conexão';check.id='checkPrintExp';
 const actions=document.createElement('div');actions.style.display='flex';actions.style.flexWrap='wrap';actions.style.gap='8px';actions.append(discover,check);
 box.style.minWidth='0';box.append(local,help,actions,message,results);grid.append(box);
 const current=()=>box.isConnected&&document.getElementById('dlg').open&&requestVersion===cfgRequest&&Boolean(token)&&!appClosed;
 const host=()=>document.getElementById('f_printexp_host'),port=()=>document.getElementById('f_printexp_port');
 let busy=false;
 let localRequest=0;
 for(const field of [host(),port()])field.addEventListener('input',()=>{if(current())message.textContent='Destino alterado. Verifique a conexão antes de salvar.'});
 async function run(button,operation){if(busy)return;busy=true;discover.disabled=check.disabled=true;try{await operation()}catch(e){if(current())message.textContent='Não foi possível consultar a rede. Você pode configurar o IPv4 manualmente.'}finally{busy=false;if(current())discover.disabled=check.disabled=false}}
 async function verify(){const snapshot=[host().value,port().value];message.textContent='Verificando a conexão TCP…';
  const r=await api('/api/printexp/check',{method:'POST',body:JSON.stringify({host:snapshot[0],port:Number(snapshot[1])})});
  if(!current()||r.stale)return;if(snapshot[0]!==host().value||snapshot[1]!==port().value){message.textContent='O destino mudou durante a verificação. Verifique novamente.';return}
  message.textContent=r.ok?r.d.message+' Use Salvar para guardar o destino.':(r.d.error||'Falha ao verificar a conexão.');
 }
 check.onclick=()=>run(check,verify);
 discover.onclick=()=>run(discover,async()=>{
  refreshLocalAddresses();
  const snapshot=[host().value,port().value];message.textContent='Procurando agentes na rede local…';results.replaceChildren();
  const r=await api('/api/printexp/discover',{method:'POST',body:'{}'});if(!current()||r.stale)return;
  if(!r.ok){message.textContent=r.d.error||'Falha na descoberta.';return}
  const items=r.d.receivers||[];
  if(!items.length){message.textContent='Nenhum agente encontrado. Confira se está ativo no computador PrintExp e se a rede permite descoberta local, ou informe o IPv4 manualmente.';return}
  function use(item){host().value=item.host;port().value=String(item.port);message.textContent='Destino preenchido. Use Salvar para manter esta configuração.'}
  if(items.length===1&&snapshot[0]===host().value&&snapshot[1]===port().value){use(items[0]);await verify();return}
  message.textContent='Selecione o endereço do computador PrintExp. As configurações atuais foram preservadas.';
  for(const item of items){const row=document.createElement('p'),choose=document.createElement('button');choose.type='button';choose.textContent=`Usar ${item.host}:${item.port} — ${item.name}`;
   choose.style.maxWidth='100%';choose.style.overflowWrap='anywhere';
   choose.onclick=()=>{if(current()&&!busy){use(item);run(check,verify)}};row.append(choose);results.append(row)}
 });
 function refreshLocalAddresses(){const request=++localRequest;
  api('/api/printexp/network').then(r=>{if(!current()||r.stale||request!==localRequest)return;local.textContent=r.ok?'IPv4 deste computador (AutoRIP): '+(r.d.local_ipv4s.map(x=>`${x.address} (${x.interface})`).join('; ')||'nenhum IPv4 privado encontrado'):'Não foi possível listar os IPv4 deste computador.'}).catch(()=>{if(current()&&request===localRequest)local.textContent='Consulta de IPv4 indisponível; configuração manual disponível.'});
 }
 refreshLocalAddresses();
}
