// HTTP real com credenciais fictícias; provedores e rede LAN simulados na UI.
const {chromium}=require(process.env.AUTORIP_PLAYWRIGHT_MODULE||'playwright');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const output=process.argv[2]||fs.mkdtempSync(path.join(os.tmpdir(),'autorip-connections-ai-'));fs.mkdirSync(output,{recursive:true});
(async()=>{
 const child=spawn(process.env.AUTORIP_PYTHON||'python',[path.join(__dirname,'_queue_smoke_app.py'),'--polling-fixtures']);
 let stderr='',browser;child.stderr.on('data',data=>stderr+=data);const lines=createInterface({input:child.stdout});
 try{
  const ready=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error(stderr||'Harness timeout')),20000);lines.once('line',line=>{clearTimeout(timer);resolve(JSON.parse(line))})});
  browser=await chromium.launch({headless:true,executablePath:process.env.AUTORIP_CHROMIUM,args:process.env.AUTORIP_NO_SANDBOX==='1'?['--no-sandbox']:[]});
  const page=await browser.newPage({viewport:{width:390,height:844},reducedMotion:'reduce'}),errors=[],statuses=[];
  page.on('pageerror',error=>errors.push(error.message));page.setDefaultTimeout(10000);
  await page.goto(ready.url);await page.waitForFunction(()=>typeof renderAiAccounts==='function');
  await page.evaluate(async()=>{stopPolling();token='queue-browser-token';await poll(true)});
  page.on('response',response=>{if(/^\/api\/(state|prints|hot-files)$/.test(new URL(response.url()).pathname))statuses.push(response.status())});
  const bytes=await page.evaluate(async()=>{await Promise.all([poll(true),pollPrints(true),pollHotFiles(true)]);let transferred=0;
   for(const resource of ['/api/state','/api/prints','/api/hot-files']){const old=await fetch(resource,{headers:{'X-Token':token}});transferred+=(await old.arrayBuffer()).byteLength}
   for(let i=0;i<10;i++)await Promise.all([poll(),pollPrints(),pollHotFiles()]);return transferred;
  });
  assert(statuses.filter(status=>status===304).length>=30);
  // Recuperar a mesma fotografia após uma falha de rede também restaura o texto de estado.
  await page.route('**/api/state',route=>route.abort('failed'));await page.evaluate(()=>poll());
  assert.equal(await page.locator('#autoTxt').innerText(),'Estado indisponível');
  await page.unroute('**/api/state');await page.evaluate(()=>poll());
  assert.equal(await page.locator('#autoTxt').innerText(),'Desligado');
  const accounts=Array.from({length:137},(_,index)=>({provider:'gemini',key:'browser-private-key-'+index,label:'Conta '+index}));
  const saved=await page.request.post(ready.url+'/api/settings',{headers:{'X-Token':'queue-browser-token'},data:{ai_accounts:accounts}});
  assert.equal(saved.status(),200);assert(!(await saved.text()).includes('browser-private-key'));
  await page.evaluate(()=>openCfg());await page.locator('.ai-account').first().waitFor();
  assert.equal(await page.locator('.ai-account').count(),50);
  assert.equal(await page.locator('.ai-key').first().inputValue(),'');
  assert.equal(await page.locator('.ai-key').first().getAttribute('type'),'password');
  for(const provider of ['manus','deepseek','gemini','gemini']){
   await page.locator('#aiNewProvider').selectOption(provider);await page.locator('#aiAddAccount').click();
   await page.locator('.ai-key').last().fill('new-private-key-'+provider);
  }
  assert((await page.locator('#aiAccountCount').innerText()).includes('141 contas'));
  // Paginação mantém os rascunhos fora do DOM sem limitar a quantidade salva.
  await page.getByRole('button',{name:'Anteriores',exact:true}).click();
  await page.getByRole('button',{name:'Próximas',exact:true}).click();
  assert.equal(await page.locator('.ai-key').last().inputValue(),'new-private-key-gemini');
  await page.getByRole('button',{name:'Salvar',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#cmsg').textContent.includes('Salvo'));
  await page.waitForFunction(()=>document.querySelector('#aiAccountCount').textContent.includes('141 contas'));
  const settings=await(await page.request.get(ready.url+'/api/settings',{headers:{'X-Token':'queue-browser-token'}})).json();
  assert.equal(settings.ai_accounts.length,141);assert(settings.ai_accounts.every(account=>account.has_key&&!account.key));
  for(const width of [390,320]){await page.setViewportSize({width,height:844});assert(await page.locator('#dlg').evaluate(node=>node.scrollWidth<=node.clientWidth));}
  await page.locator('.ai-accounts').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,'ai-accounts-320.png')});
  await page.evaluate(()=>dlg.close());await page.evaluate(()=>poll(true));
  await page.locator('#agentProvider').selectOption('gemini');
  let asked;
  await page.route('**/api/agent',async route=>{asked=route.request().postDataJSON();await route.fulfill({json:{text:'Análise simulada, sem consulta externa'}})});
  await page.locator('#agentAsk').click();await page.waitForFunction(()=>document.querySelector('#agentOut').textContent.includes('simulada'));
  assert.equal(asked.provider,'gemini');
  let active=false,posts=0;const phoneUrl='http://192.168.1.20:'+new URL(ready.url).port+'/';
  await page.route('**/api/mobile/access',async route=>{
   if(route.request().method()==='POST'){posts++;active=route.request().postDataJSON().enabled}
   await route.fulfill({json:{interfaces:[{address:'192.168.1.20',interface:'Wi-Fi'},{address:'10.0.0.20',interface:'Ethernet'}],
    url:active?phoneUrl:null,enabled:active,can_disable:active,selected_host:'',port:Number(new URL(ready.url).port)}});
  });
  await page.route('**/api/mobile/qr',route=>route.fulfill({json:{url:phoneUrl,svg:'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="40" height="40"/></svg>'}}));
  await page.getByRole('button',{name:'📱 Conectar celular',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#mobileHost').options.length===2);
  assert.equal(posts,0);await page.locator('#mobileEnable').click();
  await page.waitForFunction(()=>document.querySelector('#mobileQrUrl').textContent.startsWith('http://192.168.1.20:'));
  assert.equal(posts,1);assert.equal(await page.locator('#mobileQrUrl').innerText(),phoneUrl);
  assert(!phoneUrl.includes('token'));assert(await page.locator('#mobileQr').evaluate(image=>image.complete&&image.naturalWidth>0));
  await page.screenshot({path:path.join(output,'phone-qr-320.png')});
  await page.locator('#mobileDisable').click();await page.waitForFunction(()=>document.querySelector('#mobileQrUrl').textContent==='');assert.equal(posts,2);
  await page.evaluate(()=>{qrDlg.close();lockPanel()});
  await page.getByRole('button',{name:'📱 Conectar celular',exact:true}).click();
  await page.locator('#pw').fill('senha-de-teste');await page.locator('#pw2').fill('senha-de-teste');
  await page.getByRole('button',{name:'Entrar',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#qrDlg').open&&document.querySelector('#mobileHost').options.length===2);
  assert(!(await page.locator('#dlg').evaluate(dialog=>dialog.open)));
  assert.deepEqual(errors,[]);
  const report={passed:true,configuredAccounts:141,duplicateProvider:true,renderedPerPage:50,passwordInputs:true,keysRedacted:true,
   providerSelection:true,qrActivationExplicit:true,qrLoginResume:true,qrContainsOnlyUrl:true,mockedLanUI:true,
   unchangedBodyBytesPerRound:0,baselineBodyBytesPerRound:bytes,conditionalResponses:statuses.filter(status=>status===304).length,pageErrors:errors};
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
 }finally{if(browser)await browser.close();if(child.exitCode===null){const stopped=new Promise(resolve=>child.once('exit',resolve));child.stdin.end(JSON.stringify({operation:'stop'})+'\n');await stopped}lines.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
