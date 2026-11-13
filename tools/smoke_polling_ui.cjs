// Smoke opcional: respostas controladas, dados temporários, Playwright/Chromium.
// AUTORIP_POLLING_BASELINE=<git-ref> executa a mesma prova contra o HTML anterior.
const {chromium}=require(process.env.AUTORIP_PLAYWRIGHT_MODULE||'playwright');
const {spawn,execFileSync}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const output=process.argv[2]||fs.mkdtempSync(path.join(os.tmpdir(),'autorip-polling-ui-'));fs.mkdirSync(output,{recursive:true});
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve}};
(async()=>{
 const child=spawn(process.env.AUTORIP_PYTHON||'python',[path.join(__dirname,'_queue_smoke_app.py'),'--polling-fixtures']);
 let stderr='';child.stderr.on('data',data=>stderr+=data);const messages=[],pending=[];
 const lines=createInterface({input:child.stdout});lines.on('line',line=>{const value=JSON.parse(line);if(pending.length)pending.shift()(value);else messages.push(value)});
 const receive=()=>messages.length?Promise.resolve(messages.shift()):new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Harness timeout: '+stderr)),20000);pending.push(v=>{clearTimeout(timer);resolve(v)})});
 let browser;
 try{
  const ready=await receive(),baseline=process.env.AUTORIP_POLLING_BASELINE;
  const html=baseline?execFileSync('git',['show',baseline+':autorip/ui/index.html'],{cwd:path.join(__dirname,'..'),encoding:'utf8'}):null;
  browser=await chromium.launch({headless:true,...(process.env.AUTORIP_CHROMIUM?{executablePath:process.env.AUTORIP_CHROMIUM}:{}),args:process.env.AUTORIP_NO_SANDBOX==='1'?['--no-sandbox']:[]});
  const results=[];
  async function test(name,fn,{timers=false,livePolling=false,initialHidden=false,viewport={width:1440,height:1000}}={}){
   const page=await browser.newPage({viewport,reducedMotion:'reduce'}),errors=[];let closing=false;const originalRoute=page.route.bind(page);page.route=(pattern,handler)=>originalRoute(pattern,async route=>{try{await handler(route)}catch(error){if(!closing)throw error}});
   page.setDefaultTimeout(8000);page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
   if(html)await page.route(ready.url+'/',r=>r.fulfill({contentType:'text/html',body:html}));
   await page.addInitScript(({initialHidden})=>{
    const original=window.setInterval,clear=window.clearInterval;window.__intervals=[];window.__activeIntervals=new Set();
    window.setInterval=(...args)=>{const id=original(...args);__intervals.push(id);__activeIntervals.add(id);return id};
    window.clearInterval=id=>{__activeIntervals.delete(id);clear(id)};
    window.__setPageHidden=hidden=>{Object.defineProperty(document,'hidden',{configurable:true,value:hidden});Object.defineProperty(document,'visibilityState',{configurable:true,value:hidden?'hidden':'visible'});document.dispatchEvent(new Event('visibilitychange'))};
    if(initialHidden){Object.defineProperty(document,'hidden',{configurable:true,value:true});Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'})}
   },{initialHidden});
   try{
    await page.goto(ready.url);
    await page.evaluate(async live=>{if(!live)for(const id of __intervals)clearInterval(id);token='queue-browser-token';await Promise.all([poll(true),pollPrints(true),pollHotFiles(true)])},livePolling);
    await page.waitForFunction(()=>document.querySelectorAll('#hotFiles .hot-file').length===2&&document.querySelectorAll('#pq .pq').length===2);
    // Settle the anonymous startup state request before each controlled scenario.
    await page.evaluate(()=>poll(true));
    if(timers)await page.evaluate(()=>{setInterval(poll,1000);setInterval(pollPrints,3000);setInterval(pollHotFiles,3000)});
    const evidence=await fn(page);assert.deepEqual(errors,[]);results.push({name,passed:true,...evidence});
   }catch(e){results.push({name,passed:false,error:e.message,pageErrors:errors,...await page.evaluate(()=>window.__evidence||{}).catch(()=>({}))})}finally{closing=true;await page.close()}
  }
  await test('authenticated lists remove all login placeholder nodes',async page=>{
   assert(!await page.locator('#hotFiles').innerText().then(t=>t.includes('Faça login')));assert(!await page.locator('#pq').innerText().then(t=>t.includes('Faça login')));
   assert.equal(await page.evaluate(()=>[...document.querySelector('#hotFiles').childNodes,...document.querySelector('#pq').childNodes].filter(n=>n.nodeType===Node.TEXT_NODE&&n.textContent.trim()).length),0);
  });
  await test('unchanged hot rows preserve nodes and focus',async page=>{
   await page.evaluate(()=>{window.originalHot=document.querySelector('#hotFiles .hot-file');window.hotButton=originalHot.querySelector('button');hotButton.focus()});
   await page.evaluate(async()=>{let mutations=0;const observer=new MutationObserver(records=>mutations+=records.length);observer.observe(document.querySelector('#hotFiles'),{childList:true,subtree:true});for(let i=0;i<20;i++)await pollHotFiles();observer.disconnect();window.__evidence={polls:20,childListMutations:mutations}});
   assert(await page.evaluate(()=>originalHot===document.querySelector('#hotFiles .hot-file')&&document.activeElement===hotButton));
   return{preserved:true,...await page.evaluate(()=>__evidence)};
  });
  await test('one changed hot row preserves its neighbour',async page=>{
   await page.evaluate(()=>{window.originalHot=document.querySelector('#hotFiles .hot-file');originalHot.querySelector('button').focus()});
   await page.route('**/api/hot-files',async route=>{const data=await(await route.fetch()).json();data[1].size+=100;await route.fulfill({json:data})});
   await page.evaluate(()=>pollHotFiles());assert(await page.evaluate(()=>originalHot===document.querySelector('#hotFiles .hot-file')&&originalHot.contains(document.activeElement)));
  });
  await test('hot polling is single flight with one forced followup',async page=>{
   const started=deferred(),release=deferred();let requests=0,active=0,maxActive=0;
   await page.route('**/api/hot-files',async route=>{requests++;active++;maxActive=Math.max(maxActive,active);const response=await route.fetch();if(requests===1){started.resolve();await release.promise}active--;await route.fulfill({response})});
   await page.evaluate(()=>{window.inflight=pollHotFiles()});await started.promise;
   await page.evaluate(()=>{window.burst=Promise.all([...Array.from({length:12},()=>pollHotFiles()),...Array.from({length:8},()=>pollHotFiles(true))])});
   release.resolve();await page.evaluate(()=>Promise.all([inflight,burst]));await page.evaluate(metrics=>{window.__evidence=metrics},{requests,maximumInFlight:maxActive});assert.equal(requests,2);assert.equal(maxActive,1);return{requests,maximumInFlight:maxActive};
  });
  for(const resource of ['hot-files','prints','state'])await test('old session 401 cannot clear new session: '+resource,async page=>{
   const started=deferred(),release=deferred();await page.route('**/api/'+resource,async route=>{started.resolve();await release.promise;await route.fulfill({status:401,json:{error:'login'}})});
   await page.evaluate(r=>{window.inflight=({'hot-files':pollHotFiles,prints:pollPrints,state:poll})[r]()},resource);await started.promise;
   await page.evaluate(()=>{token='queue-browser-token-new'});release.resolve();await page.evaluate(()=>inflight);
   assert.equal(await page.evaluate(()=>token),'queue-browser-token-new');
  });
  for(const resource of ['hot-files','prints'])await test('old session data is discarded: '+resource,async page=>{
   const started=deferred(),release=deferred();await page.route('**/api/'+resource,async route=>{started.resolve();await release.promise;await route.fulfill({json:[]})});
   await page.evaluate(r=>{window.inflight=(r==='prints'?pollPrints:pollHotFiles)()},resource);await started.promise;
   await page.evaluate(()=>{token='queue-browser-token-new'});release.resolve();await page.evaluate(()=>inflight);
   assert.equal(await page.locator(resource==='prints'?'#pq .pq':'#hotFiles .hot-file').count(),2);
  });
  for(const operation of ['printed','delete'])for(const status of [404,500])await test(operation+' '+status+' preserves authentication',async page=>{
   await page.route('**/api/prints/'+operation,route=>route.fulfill({status,json:{error:'falha simulada'}}));
   await page.evaluate(op=>(op==='printed'?markPrinted:delPrint)('print-000.PRT'),operation);
   assert.equal(await page.evaluate(()=>token),'queue-browser-token');assert.equal(await page.locator('#notice').innerText(),'falha simulada');assert(!await page.locator('#dlg').evaluate(e=>e.open));
  });
  await test('network failure keeps session and reports failure',async page=>{
   await page.route('**/api/auto',route=>route.abort('failed'));await page.evaluate(()=>toggleAuto());
   assert.equal(await page.evaluate(()=>token),'queue-browser-token');assert((await page.locator('#notice').innerText()).includes('Falha de conexão'));
  });
  await test('settings response cannot repopulate a closed dialog',async page=>{
   const started=deferred(),release=deferred();await page.route('**/api/settings',async route=>{const response=await route.fetch();started.resolve();await release.promise;await route.fulfill({response})});
   await page.evaluate(()=>{document.querySelector('#dlg').showModal();window.inflight=showCfg()});await started.promise;
   await page.evaluate(()=>document.querySelector('#dlg').close());release.resolve();await page.evaluate(()=>inflight);assert.equal(await page.locator('#grid input').count(),0);
  });
  await test('current session 401 clears every private view',async page=>{
   await page.route('**/api/hot-files',route=>route.fulfill({status:401,json:{error:'login'}}));await page.evaluate(()=>pollHotFiles());
   assert.equal(await page.evaluate(()=>token),'');assert.equal(await page.locator('#jobs .job,#pq .pq,#hotFiles .hot-file').count(),0);
  });
  await test('unchanged print list makes no DOM writes',async page=>{
   await page.locator('#pq').scrollIntoViewIfNeeded();await page.waitForFunction(()=>[...document.querySelectorAll('#pq img')].every(img=>img.complete&&img.naturalWidth>0));
   const mutations=await page.evaluate(async()=>{let count=0;const observer=new MutationObserver(records=>count+=records.length);observer.observe(document.querySelector('#pq'),{childList:true,subtree:true,attributes:true,characterData:true});for(let i=0;i<20;i++)await pollPrints();observer.disconnect();return count});assert.equal(mutations,0);return{polls:20,domMutations:mutations};
  });
  await test('changed print preserves neighbour and preview',async page=>{
   await page.evaluate(()=>{window.originalPrint=document.querySelector('#pq .pq');window.originalImage=originalPrint.querySelector('img');originalPrint.querySelector('button').focus()});
   await page.route('**/api/prints',async route=>{const data=await(await route.fetch()).json();data[1].mb+=1;await route.fulfill({json:data})});await page.evaluate(()=>pollPrints());
   assert(await page.evaluate(()=>originalPrint===document.querySelector('#pq .pq')&&originalImage===originalPrint.querySelector('img')&&originalPrint.contains(document.activeElement)));
  });
  await test('next print badge changes without replacing remaining row',async page=>{
   await page.evaluate(()=>{window.remaining=document.querySelectorAll('#pq .pq')[1];remaining.querySelector('button').focus()});
   await page.route('**/api/prints',async route=>{const data=await(await route.fetch()).json();await route.fulfill({json:data.slice(1)})});await page.evaluate(()=>pollPrints());
   assert(await page.evaluate(()=>remaining===document.querySelector('#pq .pq')&&remaining.contains(document.activeElement)&&!remaining.querySelector('.nx').hidden));
  });
  await test('print reordering keeps existing nodes and keyboard focus',async page=>{
   await page.evaluate(()=>{window.moving=document.querySelectorAll('#pq .pq')[1];window.movingButton=moving.querySelector('button');movingButton.focus()});
   await page.route('**/api/prints',async route=>{const data=await(await route.fetch()).json();await route.fulfill({json:data.reverse()})});await page.evaluate(()=>pollPrints());
   assert(await page.evaluate(()=>moving===document.querySelector('#pq .pq')&&document.activeElement===movingButton));
  });
  await test('unchanged prints update relative age without replacing rows',async page=>{
   const before=await page.locator('#pq small').first().innerText();await page.evaluate(()=>{window.originalPrint=document.querySelector('#pq .pq');const real=Date.now;Date.now=()=>real()+7200000});await page.evaluate(()=>pollPrints());
   assert.notEqual(await page.locator('#pq small').first().innerText(),before);assert(await page.evaluate(()=>originalPrint===document.querySelector('#pq .pq')));
  });
  await test('forced refresh discards snapshot captured before mutation',async page=>{
   const started=deferred(),release=deferred();let requests=0;
   await page.evaluate(()=>{window.oldRow=document.querySelectorAll('#pq .pq')[1];window.resurrected=0;window.observe=new MutationObserver(()=>{if([...document.querySelectorAll('#pq .nm')].some(n=>n.textContent.includes('obsolete')))resurrected++});observe.observe(document.querySelector('#pq'),{childList:true,subtree:true})});
   await page.route('**/api/prints',async route=>{const data=await(await route.fetch()).json();requests++;if(requests===1){data[0].name='obsolete.PRT';started.resolve();await release.promise}else data.shift();await route.fulfill({json:data})});
   await page.route('**/api/prints/printed',r=>r.fulfill({json:{ok:true}}));
   await page.evaluate(()=>{window.inflight=pollPrints()});await started.promise;await page.evaluate(()=>markPrinted('print-000.PRT'));release.resolve();await page.evaluate(()=>inflight);
   assert.equal(requests,2);assert.equal(await page.evaluate(()=>resurrected),0);assert.equal(await page.locator('#pq .pq').count(),1);
  });
  await test('shutdown stops timers and ignores pending responses',async page=>{
   let after=0,closed=false;page.on('request',r=>{if(closed&&/\/api\/(state|prints|hot-files)$/.test(r.url()))after++});
   const started=deferred(),release=deferred();await page.route('**/api/prints',async route=>{const response=await route.fetch();started.resolve();await release.promise;try{await route.fulfill({response})}catch(e){if(!String(e).includes('closed'))throw e}});
   await page.route('**/api/shutdown',r=>r.fulfill({status:202,json:{ok:true}}));
   await page.evaluate(()=>{window.inflight=pollPrints()});await started.promise;await page.evaluate(()=>{notify('teste');return shutdownApp()});closed=true;release.resolve();await page.evaluate(()=>inflight);
   await page.waitForTimeout(3300);await page.evaluate(n=>{window.__evidence={requestsAfterShutdown:n}},after);assert.equal(after,0);assert.equal(await page.locator('h1').innerText(),'AutoRIP encerrado');return{requestsAfterShutdown:after};
  },{timers:true});
  const jobFixture=page=>page.evaluate(()=>{
   window.__jobs=Array.from({length:100},(_,i)=>({id:'cache-'+i,name:'arte-'+i+'.png',status:i===0?'processando':'fila',progress:0}));
   renderJobs(__jobs);window.__originalJobs=new Map([...document.querySelectorAll('#jobs .job')].map(row=>[row.dataset.jobId,row]));
  });
  for(const [device,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
   await test(`one progress update preserves ninety-nine ${device} job cards`,async page=>{
    await jobFixture(page);
    const evidence=await page.evaluate(async()=>{
     const box=document.querySelector('#jobs');__originalJobs.get('cache-3').click();const focused=__originalJobs.get('cache-1').querySelector('[data-action="pause"]');focused.focus();
     let touchedNodes=0;const observer=new MutationObserver(records=>{for(const r of records)touchedNodes+=r.addedNodes.length+r.removedNodes.length});observer.observe(box,{childList:true});
     __jobs[0].progress=.37;renderJobs(__jobs);await Promise.resolve();observer.disconnect();
     return{totalCards:box.querySelectorAll('.job').length,preservedCards:[...box.querySelectorAll('.job')].filter(row=>row===__originalJobs.get(row.dataset.jobId)).length,touchedNodes,focusedPreserved:document.activeElement===focused,selectedPreserved:box.querySelector('.selected')?.dataset.jobId==='cache-3',progress:box.querySelector('[data-job-id="cache-0"] [role="progressbar"]').getAttribute('aria-valuenow')};
    });
    await page.evaluate(e=>window.__evidence=e,evidence);assert(evidence.preservedCards>=99);assert(evidence.touchedNodes<=2);assert.equal(evidence.totalCards,100);assert(evidence.focusedPreserved);assert(evidence.selectedPreserved);assert.equal(evidence.progress,'37');return evidence;
   },{viewport});
  }
  await test('job reordering keeps cards, selection and keyboard focus',async page=>{
   await jobFixture(page);const evidence=await page.evaluate(()=>{const selected=__originalJobs.get('cache-3'),button=selected.querySelector('[data-action="pause"]');selected.click();button.focus();__jobs.reverse();renderJobs(__jobs);return{preservedCards:[...document.querySelectorAll('#jobs .job')].filter(row=>row===__originalJobs.get(row.dataset.jobId)).length,focused:document.activeElement===button,selected:document.querySelector('#jobs .selected')===selected}});
   await page.evaluate(e=>window.__evidence=e,evidence);assert.equal(evidence.preservedCards,100);assert(evidence.focused);assert(evidence.selected);return evidence;
  });
  await test('changed job controls receive focus and completion notifies once',async page=>{
   await jobFixture(page);const evidence=await page.evaluate(()=>{const row=__originalJobs.get('cache-0');row.click();row.querySelector('[data-action="pause"]').focus();__jobs[0].status='pausado';renderJobs(__jobs);const focusedAction=document.activeElement?.dataset.action;let notifications=0;celebrate=()=>notifications++;__jobs[0].status='pronto';renderJobs(__jobs);renderJobs(__jobs);__jobs[1].progress=.2;renderJobs(__jobs);return{focusedAction,notifications}});
   assert.equal(evidence.focusedAction,'resume');assert.equal(evidence.notifications,1);return evidence;
  });
  await test('removed job cards are evicted before a matching id returns',async page=>{
   await jobFixture(page);const evidence=await page.evaluate(()=>{const old=__originalJobs.get('cache-0');renderJobs(__jobs.slice(1));const removed=!old.isConnected;renderJobs(__jobs);return{removed,reusedEvictedCard:document.querySelector('[data-job-id="cache-0"]')===old,cards:document.querySelectorAll('#jobs .job').length}});assert(evidence.removed);assert(!evidence.reusedEvictedCard);assert.equal(evidence.cards,100);return evidence;
  });
  await test('locking discards cached job cards across sessions',async page=>{
   await jobFixture(page);const evidence=await page.evaluate(()=>{const old=__originalJobs.get('cache-0');lockPanel();token='queue-browser-token-new';renderJobs(__jobs);return{reusedPriorSessionCard:document.querySelector('[data-job-id="cache-0"]')===old,oldCardConnected:old.isConnected}});assert(!evidence.reusedPriorSessionCard);assert(!evidence.oldCardConnected);return evidence;
  });
  for(const [device,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
   await test(`hidden ${device} skips fifty periodic API requests`,async page=>{
    const counts={state:0,prints:0,'hot-files':0};page.on('request',r=>{const match=new URL(r.url()).pathname.match(/^\/api\/(state|prints|hot-files)$/);if(match)counts[match[1]]++});
    await page.evaluate(async()=>{__setPageHidden(true);for(let tick=0;tick<30;tick++){await poll();if(tick%3===0)await Promise.all([pollPrints(),pollHotFiles()])}});
    const evidence={simulatedStateTicks:30,simulatedListTicks:10,periodicRequests:Object.values(counts).reduce((a,b)=>a+b,0),counts};await page.evaluate(e=>window.__evidence=e,evidence);assert.equal(evidence.periodicRequests,0);return evidence;
   },{viewport});
  }
  await test('visibility stops timers and resumes exactly one set',async page=>{
   assert.equal(await page.evaluate(()=>__activeIntervals.size),3);
   await page.evaluate(()=>__setPageHidden(true));assert.equal(await page.evaluate(()=>__activeIntervals.size),0);
   const responses=Promise.all(['state','prints','hot-files'].map(resource=>page.waitForResponse(r=>new URL(r.url()).pathname==='/api/'+resource)));
   await page.evaluate(()=>__setPageHidden(false));await responses;
   await page.evaluate(()=>{__setPageHidden(false);__setPageHidden(false)});assert.equal(await page.evaluate(()=>__activeIntervals.size),3);
   return{hiddenIntervals:0,resumedIntervals:3,immediateRefreshResources:3};
  },{livePolling:true});
  await test('a page opened hidden starts without periodic timers',async page=>{
   const evidence=await page.evaluate(()=>({intervals:__activeIntervals.size,animationsPaused:document.body.classList.contains('tab-hidden')}));await page.evaluate(e=>window.__evidence=e,evidence);assert.equal(evidence.intervals,0);assert(evidence.animationsPaused);return evidence;
  },{livePolling:true,initialHidden:true});
  await test('explicit refreshes still complete while hidden',async page=>{
   let requests=0;page.on('request',r=>{if(/^\/api\/(state|prints|hot-files)$/.test(new URL(r.url()).pathname))requests++});
   await page.evaluate(async()=>{__setPageHidden(true);await Promise.all([poll(true),pollPrints(true),pollHotFiles(true)])});assert.equal(requests,3);return{explicitRequestsWhileHidden:requests};
  });
  await test('returning to a page discards a pending obsolete snapshot',async page=>{
   const started=deferred(),release=deferred();let requests=0;
   await page.evaluate(()=>{window.resurrected=0;window.observe=new MutationObserver(()=>{if([...document.querySelectorAll('#pq .nm')].some(n=>n.textContent.includes('obsolete')))resurrected++});observe.observe(document.querySelector('#pq'),{childList:true,subtree:true})});
   await page.route('**/api/prints',async route=>{const data=await(await route.fetch()).json();requests++;if(requests===1){data[0].name='obsolete.PRT';started.resolve();await release.promise}await route.fulfill({json:data})});
   await page.evaluate(()=>{window.inflight=pollPrints()});await started.promise;
   await page.evaluate(()=>{__setPageHidden(true);__setPageHidden(false)});release.resolve();await page.evaluate(()=>inflight);
   const evidence={requests,obsoleteRenders:await page.evaluate(()=>resurrected)};await page.evaluate(e=>window.__evidence=e,evidence);assert.equal(requests,2);assert.equal(evidence.obsoleteRenders,0);return evidence;
  });
  await test('visibility cannot restart a closed application',async page=>{
   await page.route('**/api/shutdown',r=>r.fulfill({status:202,json:{ok:true}}));await page.evaluate(()=>shutdownApp());
   let requests=0;page.on('request',r=>{if(/^\/api\/(state|prints|hot-files)$/.test(new URL(r.url()).pathname))requests++});
   await page.evaluate(async()=>{__setPageHidden(true);__setPageHidden(false);await Promise.all([poll(),pollPrints(),pollHotFiles()])});assert.equal(requests,0);assert.equal(await page.evaluate(()=>__activeIntervals.size),0);return{requestsAfterShutdown:requests,intervalsAfterShutdown:0};
  },{livePolling:true});
  if(!baseline){
   const openNetwork=async page=>{await page.evaluate(()=>openCfg());await page.locator('#discoverPrintExp').waitFor()};
   await test('IPv4 discovery fills a single candidate without silently saving',async page=>{
    let saves=0;await page.route('**/api/settings',async route=>{if(route.request().method()==='POST')saves++;await route.continue()});
    await page.route('**/api/printexp/discover',r=>r.fulfill({json:{receivers:[{name:'Receiver',host:'192.168.0.215',port:9100}]}}));
    await page.route('**/api/printexp/check',r=>r.fulfill({json:{reachable:true,message:'Conexão TCP estabelecida'}}));
    await openNetwork(page);await page.locator('#discoverPrintExp').click();await page.waitForFunction(()=>document.querySelector('#f_printexp_host').value==='192.168.0.215');
    assert.equal(await page.locator('#f_printexp_port').inputValue(),'9100');assert.equal(saves,0);
    await page.waitForFunction(()=>!document.querySelector('#discoverPrintExp').disabled);
    await page.locator('#discoverPrintExp').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,'printexp-ipv4-desktop.png')});
   });
   await test('multiple IPv4 candidates require selection and render labels as text',async page=>{
    await page.route('**/api/printexp/discover',r=>r.fulfill({json:{receivers:[{name:'<img src=x onerror=alert(1)>',host:'192.168.0.20',port:9100},{name:'Other',host:'192.168.0.21',port:9100}]}}));
    await openNetwork(page);await page.locator('#f_printexp_host').fill('192.168.0.99');await page.locator('#discoverPrintExp').click();await page.waitForFunction(()=>document.querySelector('#printexpNetwork').textContent.includes('Selecione'));
    assert.equal(await page.locator('#f_printexp_host').inputValue(),'192.168.0.99');assert.equal(await page.locator('#printexpNetwork img').count(),0);
   });
   await test('delayed IPv4 discovery preserves an address edited by the user',async page=>{
    const started=deferred(),release=deferred();await page.route('**/api/printexp/discover',async route=>{started.resolve();await release.promise;await route.fulfill({json:{receivers:[{name:'Receiver',host:'192.168.0.215',port:9100}]}})});
    await openNetwork(page);await page.locator('#discoverPrintExp').click();await started.promise;await page.locator('#f_printexp_host').fill('192.168.0.88');release.resolve();await page.waitForFunction(()=>!document.querySelector('#discoverPrintExp').disabled);
    assert.equal(await page.locator('#f_printexp_host').inputValue(),'192.168.0.88');
   });
   await test('IPv4 discovery after closing settings cannot change fields',async page=>{
    const started=deferred(),release=deferred();await page.route('**/api/printexp/discover',async route=>{started.resolve();await release.promise;await route.fulfill({json:{receivers:[{name:'Receiver',host:'192.168.0.215',port:9100}]}})});
    await openNetwork(page);await page.locator('#f_printexp_host').fill('192.168.0.77');await page.locator('#discoverPrintExp').click();await started.promise;await page.evaluate(()=>document.querySelector('#dlg').close());release.resolve();await page.waitForTimeout(100);
    assert.equal(await page.locator('#f_printexp_host').inputValue(),'192.168.0.77');
   });
   await test('empty IPv4 discovery preserves a manually configured destination',async page=>{
    await page.route('**/api/printexp/discover',r=>r.fulfill({json:{receivers:[]}}));await openNetwork(page);
    await page.locator('#f_printexp_host').fill('192.168.0.33');await page.locator('#discoverPrintExp').click();await page.waitForFunction(()=>!document.querySelector('#discoverPrintExp').disabled);
    assert.equal(await page.locator('#f_printexp_host').inputValue(),'192.168.0.33');assert((await page.locator('#printexpNetwork').innerText()).includes('Nenhum agente encontrado'));
   });
   await test('IPv4 discovery controls fit a mobile viewport',async page=>{
    await openNetwork(page);await page.locator('#discoverPrintExp').scrollIntoViewIfNeeded();
    for(const id of ['discoverPrintExp','checkPrintExp']){const box=await page.locator('#'+id).boundingBox();assert(box.x>=0&&box.x+box.width<=390)}
    await page.screenshot({path:path.join(output,'printexp-ipv4-mobile.png')});
   },{viewport:{width:390,height:844}});
  }
  const source=html||fs.readFileSync(path.join(__dirname,'../autorip/ui/index.html'),'utf8');const report={baseline:baseline||null,browser:browser.version(),uiSha256:crypto.createHash('sha256').update(source).digest('hex'),passed:results.every(r=>r.passed),cases:results.length,results};fs.writeFileSync(path.join(output,'browser-results.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));if(!report.passed&&!baseline)process.exitCode=1;
 }finally{if(browser)await browser.close();if(child.exitCode===null&&child.signalCode===null){const exited=new Promise(r=>child.once('exit',r));child.stdin.end(JSON.stringify({operation:'stop'})+'\n');await exited}lines.close()}
})().catch(e=>{console.error(e);process.exit(1)});
