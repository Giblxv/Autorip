// QR contém somente a URL LAN. Senhas e tokens continuam fora do QR.
let mobileQrUrl="", mobileQrObjectUrl="", mobileQrRequest=0;
window.pendingMobileConnect=false;

function clearMobileQR(){
 mobileQrUrl="";
 if(mobileQrObjectUrl)URL.revokeObjectURL(mobileQrObjectUrl);
 mobileQrObjectUrl="";$("mobileQr").removeAttribute("src");
 $("mobileQr").style.display="none";$("mobileQrUrl").textContent="";
}
window.resetMobileConnect=()=>{mobileQrRequest++;clearMobileQR();$("qrDlg").close();window.pendingMobileConnect=false};

async function renderMobileQR(request){
 const r=await api("/api/mobile/qr");
 if(r.stale||request!==mobileQrRequest||!$("qrDlg").open)return;
 if(!r.ok){$("mobileQrMessage").textContent=r.d.error||"Não foi possível gerar o QR.";return}
 clearMobileQR();mobileQrUrl=r.d.url;
 mobileQrObjectUrl=URL.createObjectURL(new Blob([r.d.svg],{type:"image/svg+xml"}));
 $("mobileQr").src=mobileQrObjectUrl;$("mobileQr").style.display="block";
 $("mobileQrUrl").textContent=r.d.url;
 $("mobileQrMessage").textContent="Acesso ativo. Escaneie o QR e faça login no telefone.";
}

async function showMobileQR(){
 if(!token){window.pendingMobileConnect=true;notify("Entre ou crie sua senha para configurar o celular.");openCfg();return}
 const request=++mobileQrRequest,dialog=$("qrDlg");
 if(!dialog.open)dialog.showModal();clearMobileQR();
 $("mobileQrMessage").textContent="Consultando interfaces de rede…";
 const r=await api("/api/mobile/access");
 if(r.stale||request!==mobileQrRequest||!dialog.open)return;
 if(!r.ok){$("mobileQrMessage").textContent=r.d.error||"Não foi possível consultar a rede.";return}
 const select=$("mobileHost");select.replaceChildren();
 for(const item of r.d.interfaces){const option=document.createElement("option");option.value=item.address;option.textContent=item.address+" — "+item.interface;select.appendChild(option)}
 const current=r.d.url?new URL(r.d.url).hostname:r.d.selected_host;
 if([...select.options].some(option=>option.value===current))select.value=current;
 $("mobileEnable").disabled=!select.options.length;$("mobileDisable").hidden=!r.d.can_disable;
 if(r.d.url)await renderMobileQR(request);
 else $("mobileQrMessage").textContent=select.options.length?
  "Escolha o IPv4 da rede do telefone e clique em Ativar acesso e gerar QR.":
  "Nenhum IPv4 privado encontrado. Conecte o computador ao Wi-Fi/Ethernet e atualize os IPs.";
}

async function setMobileAccess(enabled){
 const request=++mobileQrRequest;$("mobileEnable").disabled=true;
 $("mobileQrMessage").textContent=enabled?"Ativando acesso pela rede local…":"Desativando acesso…";
 const r=await api("/api/mobile/access",{method:"POST",body:JSON.stringify({enabled,host:$("mobileHost").value})});
 if(r.stale||request!==mobileQrRequest||!$("qrDlg").open)return;
 if(!r.ok){$("mobileEnable").disabled=!$("mobileHost").options.length;$("mobileQrMessage").textContent=r.d.error||"Não foi possível alterar o acesso.";return}
 await showMobileQR();
}
async function copyMobileUrl(){
 if(!mobileQrUrl)return;
 try{await navigator.clipboard.writeText(mobileQrUrl);notify("Endereço copiado.")}
 catch{notify("Copie o endereço exibido manualmente.")}
}
$("qrDlg").addEventListener("close",()=>{mobileQrRequest++;clearMobileQR()});
$("dlg").addEventListener("close",()=>{window.pendingMobileConnect=false});
