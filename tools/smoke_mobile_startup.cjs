// Mede os bytes JS realmente pedidos na abertura. QR nativo é simulado separadamente.
const {chromium}=require(process.env.AUTORIP_PLAYWRIGHT_MODULE||'playwright');
const {execFileSync}=require('node:child_process');
const http=require('node:http'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const output=process.argv[2]||fs.mkdtempSync(path.join(os.tmpdir(),'autorip-mobile-startup-'));fs.mkdirSync(output,{recursive:true});
const ref=process.env.AUTORIP_MOBILE_BASELINE||'5827ec9',root=path.resolve(__dirname,'../mobile/public');
const old=new Map(['index.html','app.js','brand-mark.png'].map(name=>[name,execFileSync('git',['show',ref+':mobile/public/'+name],{cwd:path.resolve(__dirname,'..')})]));
(async()=>{
 const service=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost');let body;
  if(url.pathname==='/connected/'){res.end('Conectado');return}
  const match=url.pathname.match(/^\/(baseline|candidate)\/(.*)$/);
  if(!match){res.writeHead(404);res.end();return}
  const file=match[2]||'index.html';
  if(match[1]==='baseline')body=old.get(file);
  else{const target=path.resolve(root,file);if(target.startsWith(root+path.sep)&&fs.existsSync(target)&&fs.statSync(target).isFile())body=fs.readFileSync(target)}
  if(!body){res.writeHead(404);res.end();return}
  res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.png')?'image/png':'text/html');res.end(body);
 });
 await new Promise(resolve=>service.listen(0,'127.0.0.1',resolve));const base='http://127.0.0.1:'+service.address().port;
 let browser;const errors=[];
 try{
  browser=await chromium.launch({headless:true,executablePath:process.env.AUTORIP_CHROMIUM,args:process.env.AUTORIP_NO_SANDBOX==='1'?['--no-sandbox']:[]});
  const sizes={};let lazyRequests;
  for(const version of ['baseline','candidate']){
   const page=await browser.newPage(),responses=[];
   page.on('pageerror',error=>errors.push(error.message));
   page.on('response',response=>{if(new URL(response.url()).pathname.endsWith('.js'))responses.push(response.body().then(body=>({url:response.url(),bytes:body.length})))});
   await page.goto(base+'/'+version+'/');await page.waitForFunction(()=>typeof document.querySelector('#connect').onclick==='function');
   const startup=await Promise.all(responses);sizes[version]={bytes:startup.reduce((sum,item)=>sum+item.bytes,0),requests:startup.length,files:startup};
   if(version==='candidate'){
    assert.equal(startup.length,1);assert(startup[0].url.endsWith('/bundle/app.js'));
    await page.locator('#scan').click();await page.waitForFunction(()=>!document.querySelector('#scan').disabled);
    lazyRequests=(await Promise.all(responses)).length-startup.length;assert(lazyRequests>=2);
   }
   await page.close();
  }
  const page=await browser.newPage({viewport:{width:320,height:640}});page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(()=>{
   if(location.pathname.startsWith('/candidate/'))localStorage.setItem('autorip.server.urls',JSON.stringify(Array.from({length:10000},(_,index)=>'http://192.168.1.'+(index+1))));
   Storage.prototype.setItem=()=>{throw new DOMException('Storage blocked','SecurityError')};
  });
  await page.goto(base+'/candidate/');await page.waitForFunction(()=>document.querySelector('#connect').onclick!==null);
  assert.equal(await page.locator('#recentList button').count(),5);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.locator('#url').fill(base+'/connected/?token=private');await page.locator('#connect').click();assert((await page.locator('#error').innerText()).includes('sem usuário'));
  await page.locator('#url').fill(base+'/connected');await page.locator('#connect').click();await page.waitForURL(base+'/connected/');
  // Simula apenas o contrato do plugin de câmera; não substitui teste num Android físico.
  const scanner=await browser.newPage();scanner.on('pageerror',error=>errors.push(error.message));
  await scanner.route('**/candidate/bundle/chunks/esm-*.js',route=>route.fulfill({contentType:'application/javascript',body:
   `export const BarcodeFormat={QrCode:'QR_CODE'};export const BarcodeScanner={isSupported:async()=>({supported:true}),checkPermissions:async()=>({camera:'granted'}),scan:async()=>({barcodes:[{format:'QR_CODE',rawValue:window.testQR}]})};`}));
  await scanner.goto(base+'/candidate/');await scanner.waitForFunction(()=>document.querySelector('#scan').onclick!==null);
  await scanner.evaluate(url=>window.testQR=url,base+'/connected/?token=private');await scanner.locator('#scan').click();
  await scanner.waitForFunction(()=>document.querySelector('#error').textContent.includes('O QR não contém'));
  await scanner.evaluate(url=>window.testQR=url,base+'/connected/');await scanner.locator('#scan').click();await scanner.waitForURL(base+'/connected/');
  assert.deepEqual(errors,[]);
  const report={passed:true,baseline:ref,startup:sizes,initialJsReductionPercent:100*(1-sizes.candidate.bytes/sizes.baseline.bytes),
   scannerChunksBeforeClick:0,scannerRequestsAfterClick:lazyRequests,recentButtonsFor10000Entries:5,storageFailureDoesNotBlockConnection:true,
   manualAndQrRejectSecretsInQuery:true,mockedScannerConnection:true,physicalAndroidTested:false,pageErrors:errors};
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
 }finally{if(browser)await browser.close();await new Promise(resolve=>service.close(resolve))}
})().catch(error=>{console.error(error);process.exitCode=1});
