/* Planejamento explícito: não participa do polling ou da fila de RIP. */
let sheetVersion=0,sheetLoadRequest=0,sheetComputeRequest=0,sheetPlan=null,sheetObjectURL=null;
let sheetLoading=false,sheetComputing=false;
function sheetButtons(){document.getElementById("sheetCompute").disabled=sheetLoading||sheetComputing;document.getElementById("sheetRefresh").disabled=sheetLoading||sheetComputing}

function invalidateSheetPlan(){
 sheetVersion++;sheetPlan=null;
 if(sheetObjectURL){URL.revokeObjectURL(sheetObjectURL);sheetObjectURL=null}
 document.getElementById("sheetPreview").removeAttribute("src");
 document.getElementById("sheetPreview").hidden=true;
 document.getElementById("sheetSvg").removeAttribute("href");
 document.getElementById("sheetSvg").hidden=true;
 document.getElementById("sheetJson").hidden=true;
 document.getElementById("sheetSummary").textContent="";
}
function resetSheetPlanner(){
 invalidateSheetPlan();sheetLoadRequest++;sheetComputeRequest++;
 const dlg=document.getElementById("sheetDlg");if(dlg.open)dlg.close();
 document.getElementById("sheetSources").replaceChildren();
 document.getElementById("sheetMessage").textContent="";
 document.getElementById("sheetCount").textContent="0 peças selecionadas";
 sheetLoading=sheetComputing=false;sheetButtons();
}
function sheetSelection(){
 return [...document.getElementById("sheetSources").children].filter(row=>row.querySelector("input[type=checkbox]").checked)
  .map(row=>({name:row.dataset.name,quantity:Number(row.querySelector(".sheet-quantity").value),width_cm:row.querySelector(".sheet-width").value||null}));
}
async function openSheetPlanner(){
 if(!token){openCfg();return}
 const dlg=document.getElementById("sheetDlg");if(!dlg.open)dlg.showModal();
 await loadSheetSources();
}
async function loadSheetSources(){
 if(sheetComputing)return;
 const request=++sheetLoadRequest;invalidateSheetPlan();
 sheetLoading=true;sheetButtons();document.getElementById("sheetSources").replaceChildren();document.getElementById("sheetCount").textContent="0 peças selecionadas";
 document.getElementById("sheetMessage").textContent="Consultando artes…";
 try{
  const r=await api("/api/hot-files");
  if(r.stale||r.session!==token||request!==sheetLoadRequest||!document.getElementById("sheetDlg").open)return;
  if(!r.ok){document.getElementById("sheetMessage").textContent=r.d.error||"Não foi possível consultar as artes.";return}
  const rows=[];
  for(const file of r.d){
   const row=document.createElement("tr");row.dataset.name=file.name;
   const nameCell=document.createElement("td"),label=document.createElement("label"),check=document.createElement("input");
   check.type="checkbox";check.setAttribute("aria-label","Selecionar "+file.name);const filename=document.createElement("span");filename.className="sheet-name";filename.title=file.name;filename.textContent=file.name;label.append(check,filename);nameCell.append(label);row.append(nameCell);
   for(const [className,value,max,placeholder,caption] of [["sheet-quantity","1","100","","Quantidade de "],["sheet-width","","300","auto","Largura de "]]){
    const td=document.createElement("td"),input=document.createElement("input");input.className=className;input.type="number";input.value=value;input.max=max;input.min=className==="sheet-quantity"?"1":"0.001";input.step=className==="sheet-quantity"?"1":"any";input.placeholder=placeholder;input.required=className==="sheet-quantity";input.disabled=true;input.setAttribute("aria-label",caption+file.name);td.append(input);row.append(td);
   }
   rows.push(row);
  }
  document.getElementById("sheetSources").replaceChildren(...rows);
  document.getElementById("sheetCount").textContent="0 peças selecionadas";
  document.getElementById("sheetMessage").textContent=rows.length?"Selecione as artes para calcular o encaixe.":"Nenhuma arte na hot folder. Salve imagens na pasta de entrada e atualize.";
 }finally{if(request===sheetLoadRequest){sheetLoading=false;sheetButtons()}}
}
async function computeSheetPlan(event){
 event.preventDefault();if(sheetLoading||sheetComputing)return;const items=sheetSelection();
 if(!items.length){document.getElementById("sheetMessage").textContent="Selecione pelo menos uma arte.";return}
 const request=++sheetComputeRequest;invalidateSheetPlan();const version=sheetVersion;
 sheetComputing=true;sheetButtons();
 document.getElementById("sheetMessage").textContent="Calculando encaixe…";
 try{
  const r=await api("/api/layout/plan",{method:"POST",body:JSON.stringify({items,sheet_width_cm:Number(document.getElementById("sheetWidth").value),margin_cm:Number(document.getElementById("sheetMargin").value),gap_cm:Number(document.getElementById("sheetGap").value),allow_rotation:document.getElementById("sheetRotate").checked})});
  if(r.stale||r.session!==token||request!==sheetComputeRequest||version!==sheetVersion||!document.getElementById("sheetDlg").open)return;
  if(!r.ok){document.getElementById("sheetMessage").textContent=r.d.error||"Não foi possível calcular o encaixe.";return}
  sheetPlan=r.d;sheetObjectURL=URL.createObjectURL(new Blob([r.d.svg],{type:"image/svg+xml"}));
  const preview=document.getElementById("sheetPreview");preview.src=sheetObjectURL;preview.hidden=false;
  const svg=document.getElementById("sheetSvg");svg.href=sheetObjectURL;svg.hidden=false;document.getElementById("sheetJson").hidden=false;
  const number=value=>Number(value).toLocaleString("pt-BR",{maximumFractionDigits:2});
  document.getElementById("sheetSummary").textContent=`Folha: ${number(r.d.sheet_width_cm)} × ${number(r.d.sheet_height_cm)} cm · Aproveitamento: ${number(r.d.utilization*100)}% · ${r.d.items.length} peças`;
  document.getElementById("sheetMessage").textContent="Planejamento pronto. As posições e rotações estão no arquivo JSON.";
 }finally{if(request===sheetComputeRequest){sheetComputing=false;sheetButtons()}}
}
function initSheetPlanner(){
 document.getElementById("sheetForm").addEventListener("submit",computeSheetPlan);
 document.getElementById("sheetRefresh").addEventListener("click",loadSheetSources);
 document.getElementById("sheetForm").addEventListener("input",event=>{
  invalidateSheetPlan();document.getElementById("sheetMessage").textContent="Calcule novamente após editar as opções.";
  const row=event.target.closest("tr");if(row){const enabled=row.querySelector("input[type=checkbox]").checked;for(const input of row.querySelectorAll("input[type=number]"))input.disabled=!enabled}
  const count=sheetSelection().reduce((sum,item)=>sum+item.quantity,0);document.getElementById("sheetCount").textContent=`${Number.isFinite(count)?count:0} peças selecionadas`;
 });
 document.getElementById("sheetDlg").addEventListener("close",()=>{sheetLoadRequest++;sheetComputeRequest++;invalidateSheetPlan();sheetLoading=sheetComputing=false;sheetButtons()});
 document.getElementById("sheetJson").addEventListener("click",()=>{
  if(!sheetPlan)return;const url=URL.createObjectURL(new Blob([JSON.stringify(sheetPlan,null,2)],{type:"application/json"}));
  const link=document.createElement("a");link.href=url;link.download="AutoRIP-planejamento.json";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 });
}
