// Smoke opcional: Playwright/Chromium e dados temporários, sem impressora.
const {chromium}=require(process.env.AUTORIP_PLAYWRIGHT_MODULE||'playwright');
const {spawn,spawnSync}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const assert=require('node:assert/strict');
const output=process.argv[2]||fs.mkdtempSync(path.join(os.tmpdir(),'autorip-thumbnail-ui-'));fs.mkdirSync(output,{recursive:true});
(async()=>{
 const child=spawn(process.env.AUTORIP_PYTHON||'python',[path.join(__dirname,'_queue_smoke_app.py'),'--thumbnail-fixtures']);
 let stderr='';child.stderr.on('data',data=>stderr+=data);
 const messages=[],pending=[];const lines=createInterface({input:child.stdout});
 lines.on('line',line=>{const value=JSON.parse(line);if(pending.length)pending.shift()(value);else messages.push(value)});
 const receive=()=>messages.length?Promise.resolve(messages.shift()):new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(new Error('Harness timeout: '+stderr)),20000);pending.push(value=>{clearTimeout(timeout);resolve(value)})});
 const command=async operation=>{child.stdin.write(JSON.stringify({operation})+'\n');return receive()};
 let browser;
 try{
  const ready=await receive();
  browser=await chromium.launch({headless:true,...(process.env.AUTORIP_CHROMIUM?{executablePath:process.env.AUTORIP_CHROMIUM}:{}),args:process.env.AUTORIP_NO_SANDBOX==='1'?['--no-sandbox']:[]});
  const errors=[];
  async function login(page){
   await page.goto(ready.url);await page.evaluate(()=>{token='queue-browser-token';return Promise.all([poll(),pollPrints(),pollHotFiles()])});
   await page.waitForFunction(()=>document.querySelectorAll('#jobs img').length===100&&document.querySelectorAll('#pq img').length===240);
  }
  let baselineRequests=null;
  if(process.env.AUTORIP_UI_BASELINE){
   const baseline=spawnSync('git',['show',process.env.AUTORIP_UI_BASELINE+':autorip/ui/index.html'],{cwd:path.join(__dirname,'..'),encoding:'utf8'});
   assert.equal(baseline.status,0,baseline.stderr);
   const old=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
   old.on('pageerror',error=>errors.push(error.message));
   await old.route(ready.url+'/',route=>route.fulfill({contentType:'text/html',body:baseline.stdout}));
   const requests=[];old.on('request',request=>{if(request.url().includes('/api/thumb?'))requests.push(request.url())});
   await login(old);
   await old.waitForFunction(()=>[...document.querySelectorAll('#jobs img,#pq img')].every(image=>image.complete&&image.naturalWidth>0));
   baselineRequests=requests.length;await old.close();
  }
  const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  page.on('pageerror',error=>errors.push(error.message));
  const requests=[];let active=0,maximum=0,resetting=false;
  await page.route('**/api/thumb?*',async route=>{
   active++;maximum=Math.max(maximum,active);requests.push(route.request().url());
   try{const response=await route.fetch();await new Promise(resolve=>setTimeout(resolve,180));await route.fulfill({response})}
   catch(error){if(!page.isClosed()&&!resetting&&!String(error).includes('closed'))throw error}
   finally{active--}
  });
  await login(page);
  // Troca os cards enquanto ainda há respostas pendentes: reaproveite a requisição.
  await page.waitForFunction(()=>thumbnailActive.size>0);
  await command('tick');await page.evaluate(()=>poll());
  await page.waitForFunction(()=>thumbnailActive.size===0&&thumbnailQueue.size===0&&document.querySelector('#jobs img').naturalWidth>0);
  const cold=requests.length;
  assert(cold>0&&cold<25,'Carregou imagens fora da área visível: '+cold);
  assert(maximum<=4);
  assert.equal(new Set(requests).size,requests.length,'Repetiu requisição ao substituir cards em voo');
  await page.screenshot({path:path.join(output,'desktop.png')});
  const pendingCold=await page.evaluate(()=>thumbnailPending.size);assert(pendingCold>250);
  await page.evaluate(()=>{window.firstThumbnail=document.querySelector('#jobs img');return poll()});
  assert(await page.evaluate(()=>firstThumbnail===document.querySelector('#jobs img')));
  assert.equal(requests.length,cold);
  await page.locator('#jobs').evaluate(element=>element.scrollTop=element.scrollHeight);
  await page.waitForFunction(()=>{const images=document.querySelectorAll('#jobs img');return images[images.length-1].complete&&images[images.length-1].naturalWidth>0});
  assert(requests.length>cold&&requests.length<40);
  await page.locator('#pq .pq').last().scrollIntoViewIfNeeded();
  await page.waitForFunction(()=>{const images=document.querySelectorAll('#pq img');return images[images.length-1].complete&&images[images.length-1].naturalWidth>0});
  const afterScroll=requests.length;assert(afterScroll<50&&maximum<=4);
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.locator('#pq .pq').last().scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,'mobile.png')});
  await page.setViewportSize({width:320,height:640});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  const leaks=await page.evaluate(()=>{const items=Array.from({length:100},(_,i)=>({id:'synthetic-'+i,name:'Arte',status:'fila',progress:0,thumb:'/api/thumb?id=preview-'+(i%50)}));for(let i=0;i<30;i++)renderJobs(items);return{pending:thumbnailPending.size,queued:thumbnailQueue.size,active:thumbnailActive.size}});
  assert(leaks.pending<=340&&leaks.queued<=340&&leaks.active<=4);
  const memory=await page.evaluate(()=>{resetThumbnails();const blob=new Blob([new Uint8Array(3*1024*1024)],{type:'image/jpeg'});for(let i=0;i<4;i++)rememberThumbnail('memory-'+i,blob);return{bytes:thumbnailCacheBytes,entries:thumbnailCache.size}});
  assert(memory.bytes<=8*1024*1024&&memory.entries===2);
  const cap=await page.evaluate(()=>{resetThumbnails();for(let i=0;i<100;i++)rememberThumbnail('entry-'+i,new Blob(['small'],{type:'image/jpeg'}));return thumbnailCache.size});
  assert.equal(cap,64);
  const expired=await page.evaluate(()=>{resetThumbnails();rememberThumbnail('expired',new Blob(['old'],{type:'image/jpeg'}));thumbnailCache.get('expired').time=Date.now()-60001;return{blob:cachedThumbnail('expired'),bytes:thumbnailCacheBytes,entries:thumbnailCache.size}});
  assert.deepEqual(expired,{blob:null,bytes:0,entries:0});
  await page.evaluate(()=>{window.staleImage=document.createElement('img');staleImage.style.cssText='position:fixed;top:10px;left:10px;width:96px;height:64px;z-index:1000';document.body.appendChild(staleImage);privateThumbnail(staleImage,'/api/thumb?id=preview-0&test=session-reset')});
  await page.waitForFunction(()=>thumbnailActive.size>0);resetting=true;
  await page.evaluate(()=>{token='';resetThumbnails()});
  await page.waitForFunction(()=>thumbnailActive.size===0);
  assert(await page.evaluate(()=>!staleImage.getAttribute('src')),'Resposta antiga pintou imagem após troca de sessão');
  const cleared=await page.evaluate(()=>({pending:thumbnailPending.size,queued:thumbnailQueue.size,cache:thumbnailCache.size,bytes:thumbnailCacheBytes}));
  assert.deepEqual(cleared,{pending:0,queued:0,cache:0,bytes:0});
  const fallback=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  fallback.on('pageerror',error=>errors.push(error.message));
  await fallback.addInitScript(()=>{window.IntersectionObserver=undefined});await login(fallback);
  await fallback.waitForFunction(()=>[...document.querySelectorAll('#jobs img,#pq img')].every(image=>image.complete&&image.naturalWidth>0));
  await fallback.close();
  assert.deepEqual(errors,[]);
  const report={passed:true,imagesInDom:340,baselineRequests,coldRequests:cold,requestsAfterScroll:afterScroll,
   maximumConcurrentFetches:maximum,deferredImages:pendingCold,inflightRequestSharedAcrossRender:true,idleDomPreserved:true,
   observerCleanupAfter30Renders:leaks,cacheByteLimit:8*1024*1024,cacheEntriesAfterFour3MiBBlobs:memory.entries,
   cacheEntryLimit:cap,expiryReleasesBytes:true,sessionReset:cleared,inflightResetPreventsStaleImage:true,
   observerUnavailableFallback:true,noOverflow390:true,noOverflow320:true,pageErrors:errors};
  fs.writeFileSync(path.join(output,'browser-results.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
 }finally{if(browser)await browser.close();if(child.exitCode===null&&child.signalCode===null){const exited=new Promise(resolve=>child.once('exit',resolve));child.stdin.end(JSON.stringify({operation:'stop'})+'\n');await exited}lines.close()}
})().catch(error=>{console.error(error);process.exit(1)});
