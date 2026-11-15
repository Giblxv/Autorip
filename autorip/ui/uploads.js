// Envia os objetos File diretamente; não duplica artes grandes em base64/ArrayBuffer.
let uploadFiles=[],uploadRunning=false,uploadEpoch=0,uploadController=null;
window.pendingUploadOpen=false;

function uploadResponse(path,options,headers,signal,keepAlive){
 return new Promise((resolve,reject)=>{
  const xhr=new XMLHttpRequest();
  const abort=()=>xhr.abort();
  function finish(error,response){
   signal.removeEventListener("abort",abort);xhr.onload=xhr.onerror=xhr.onabort=xhr.onprogress=xhr.upload.onprogress=null;
   if(error)reject(error);else resolve(response);
  }
  if(signal.aborted){reject(new DOMException("Envio interrompido","AbortError"));return}
  xhr.open("POST",path);for(const [key,value] of Object.entries(headers))xhr.setRequestHeader(key,value);
  xhr.onload=()=>finish(null,new Response(xhr.responseText,{status:xhr.status,headers:{"Content-Type":xhr.getResponseHeader("Content-Type")||"application/json"}}));
  xhr.onerror=()=>finish(new Error("Falha de conexão durante o envio"));
  xhr.onabort=()=>finish(new DOMException("Envio interrompido","AbortError"));
  xhr.onprogress=keepAlive;
  xhr.upload.onprogress=event=>{keepAlive();options.onUploadProgress(event)};
  signal.addEventListener("abort",abort,{once:true});
  try{xhr.send(options.body)}catch(error){finish(error)}
 });
}

function uploadControls(){
 $("pickUploadFiles").disabled=$("pickUploadPhotos").disabled=$("uploadWidth").disabled=uploadRunning;
 $("sendUpload").disabled=uploadRunning||!uploadFiles.length;
}
function renderUploadSelection(){
 const list=$("uploadSelection");list.replaceChildren();
 for(const file of uploadFiles.slice(0,100)){const row=document.createElement("li");row.textContent=file.name+" · "+humanSize(file.size);list.append(row)}
 const bytes=uploadFiles.reduce((sum,file)=>sum+file.size,0);
 $("uploadSummary").textContent=uploadFiles.length?`${uploadFiles.length} arquivo(s) · ${humanSize(bytes)}`+(uploadFiles.length>100?" · exibindo os primeiros 100":""):"";
 uploadControls();
}
window.resetUploads=()=>{
 uploadEpoch++;uploadController?.abort();uploadController=null;uploadRunning=false;uploadFiles=[];window.pendingUploadOpen=false;
 $("file").value=$("uploadPhotos").value="";$("uploadDlg").close();renderUploadSelection();
 $("uploadStatus").textContent="Nenhum arquivo selecionado.";$("uploadProgress").hidden=true;$("uploadProgress").value=0;
};
function openUpload(){
 if(appClosed)return;
 if(!token){window.pendingUploadOpen=true;notify("Entre para enviar arquivos do seu aparelho.");openCfg();return}
 if(!uploadRunning)$("uploadWidth").value=$("wcm").value;
 if(!$("uploadDlg").open)$("uploadDlg").showModal();renderUploadSelection();
}
function pickUploadFiles(photos){
 if(uploadRunning)return;
 $(photos?"uploadPhotos":"file").click();
}
function selectUploadFiles(files){
 if(uploadRunning){notify("Aguarde o envio atual terminar.");return}
 if(!token){openUpload();return}
 const selected=Array.from(files);if(!selected.length)return;
 const invalid=selected.find(file=>!/^.+\.(png|jpe?g|tiff?)$/i.test(file.name)||!file.size);
 if(invalid){notify("Selecione arquivos PNG, JPEG ou TIFF válidos e não vazios.");return}
 uploadFiles=selected;$("file").value=$("uploadPhotos").value="";
 $("uploadProgress").hidden=true;$("uploadProgress").value=0;
 $("uploadStatus").textContent="Confira os arquivos e toque em Enviar para a fila de RIP.";openUpload();
}
async function sendSelectedUploads(){
 if(uploadRunning||!uploadFiles.length)return;
 if(!token){openUpload();return}
 const width=$("uploadWidth").value;
 if(width&&(!Number.isFinite(Number(width))||Number(width)<=0||Number(width)>300)){$("uploadStatus").textContent="Informe uma largura maior que zero e até 300 cm.";return}
 const session=token,epoch=++uploadEpoch,batch=[...uploadFiles],total=batch.reduce((sum,file)=>sum+file.size,0);
 const current=()=>!appClosed&&token===session&&epoch===uploadEpoch;
 uploadController=new AbortController();uploadRunning=true;uploadControls();$("wcm").value=width;
 $("uploadProgress").hidden=false;$("uploadProgress").value=0;
 let sent=0,bytes=0;
 try{
  for(const file of batch){
   if(!current())return;
   $("uploadStatus").textContent=`Enviando ${sent+1}/${batch.length}: ${file.name}`;
   const r=await api(`/api/upload?name=${encodeURIComponent(file.name)}&width=${encodeURIComponent(width)}`,{
    method:"POST",body:file,signal:uploadController.signal,
    onUploadProgress:event=>{if(!current())return;const loaded=Math.min(event.loaded,file.size);$("uploadProgress").value=(bytes+loaded)/total;
     $("uploadStatus").textContent=loaded>=file.size?`Validando ${sent+1}/${batch.length} e adicionando à fila: ${file.name}`:
      `Enviando ${sent+1}/${batch.length}: ${file.name} · ${humanSize(loaded)} de ${humanSize(file.size)}`}
   });
   if(!current()||r.stale)return;
   if(!r.ok){$("uploadStatus").textContent=`${sent} de ${batch.length} enviado(s). ${file.name}: ${r.d.error||"Falha no envio; confira a fila antes de tentar novamente."}`;return}
   sent++;bytes+=file.size;uploadFiles.shift();$("uploadProgress").value=bytes/total;
  }
  if(current()){$("uploadStatus").textContent=`${sent} arquivo(s) enviado(s) e adicionado(s) à fila de RIP.`;notify("Artes recebidas pelo AutoRIP.")}
 }finally{
  if(current()){uploadController=null;uploadRunning=false;renderUploadSelection();poll(true)}
 }
}
$("file").onchange=event=>selectUploadFiles(event.target.files);
$("uploadPhotos").onchange=event=>selectUploadFiles(event.target.files);
$("dlg").addEventListener("close",()=>window.pendingUploadOpen=false);
