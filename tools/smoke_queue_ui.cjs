// Smoke opcional: requer Playwright/Chromium; usa somente dados temporários.
// AUTORIP_PYTHON=.venv/bin/python node tools/smoke_queue_ui.cjs /tmp/queue-ui
const {chromium}=require(process.env.AUTORIP_PLAYWRIGHT_MODULE||'playwright');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const path=require('node:path'),os=require('node:os');
const root=process.argv[2]||fs.mkdtempSync(path.join(os.tmpdir(),'autorip-queue-ui-'));fs.mkdirSync(root,{recursive:true});
(async()=>{
 const service=spawn(process.env.AUTORIP_PYTHON||'python',[path.join(__dirname,'_queue_smoke_app.py')]);
 let stderr='';service.stderr.on('data',d=>stderr+=d.toString());
 const pending=[],buffer=[];
 const lines=createInterface({input:service.stdout});
 lines.on('line',line=>{const value=JSON.parse(line);if(pending.length)pending.shift()(value);else buffer.push(value)});
 const receive=()=>buffer.length?Promise.resolve(buffer.shift()):new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(new Error('Harness timeout: '+stderr)),20000);pending.push(value=>{clearTimeout(timeout);resolve(value)})});
 const command=async operation=>{service.stdin.write(JSON.stringify({operation})+'\n');return receive()};
 let browser;
 try{
  const ready=await receive();
  browser=await chromium.launch({headless:true,...(process.env.AUTORIP_CHROMIUM?{executablePath:process.env.AUTORIP_CHROMIUM}:{}),args:process.env.AUTORIP_NO_SANDBOX==='1'?['--no-sandbox']:[]});
  const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(ready.url);
  await page.evaluate(()=>{token='queue-browser-token';return poll()});
  await page.waitForFunction(()=>document.querySelectorAll('#jobs .job').length===100);
  await page.evaluate(()=>Promise.all([pollPrints(),pollHotFiles()]));
  assert.equal(await page.locator('#intro').evaluate(e=>getComputedStyle(e).display),'none');
  assert.equal(await page.evaluate(()=>document.getAnimations().length),0);
  assert.equal(await page.locator('#ripCount').innerText(),'100 / 100');
  const rejected=await page.request.post(ready.url+'/api/upload?name=full.png',{data:Buffer.from('full'),headers:{'X-Token':'queue-browser-token'}});
  assert.equal(rejected.status(),429);assert((await rejected.json()).error.includes('Fila cheia'));
  const job=page.locator(`.job[data-job-id="${ready.first_id}"]`);
  await job.locator('span').first().click();
  await job.getByRole('button',{name:'Pausar arte-000.png',exact:true}).focus();
  const before=await page.locator('#jobs').evaluate(e=>e.scrollTop);
  assert(before>0);
  await page.evaluate(()=>{window.queueMutations=0;window.queueObserver=new MutationObserver(records=>queueMutations+=records.filter(r=>r.target===document.getElementById('jobs')&&r.type==='childList').length);queueObserver.observe(document.getElementById('jobs'),{childList:true})});
  await command('tick');await page.evaluate(()=>poll());
  await page.waitForFunction(id=>document.querySelector(`[data-job-id="${id}"] [role=progressbar]`).getAttribute('aria-valuenow')==='37',ready.first_id);
  assert.equal(await page.evaluate(()=>document.activeElement?.dataset.action),'pause');
  assert.equal(await page.evaluate(()=>document.activeElement.closest('.job').dataset.jobId),ready.first_id);
  assert.equal(await page.locator('#jobs .selected').getAttribute('data-job-id'),ready.first_id);
  assert(Math.abs(before-await page.locator('#jobs').evaluate(e=>e.scrollTop))<3);
  assert.equal(await page.evaluate(()=>queueMutations),1);
  await page.evaluate(()=>window.queueCard=document.querySelector('#jobs .job'));
  await page.evaluate(()=>poll());
  assert(await page.evaluate(()=>queueCard===document.querySelector('#jobs .job')));
  await page.keyboard.press('Enter');
  await job.getByRole('button',{name:'Retomar arte-000.png',exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>document.activeElement?.dataset.action),'resume');
  await page.keyboard.press('Enter');
  await job.getByRole('button',{name:'Pausar arte-000.png',exact:true}).waitFor();
  assert.equal((await command('snapshot')).queued,100);
  await job.getByRole('button',{name:'Pausar arte-000.png',exact:true}).click();
  await job.getByRole('button',{name:'Retomar arte-000.png',exact:true}).waitFor();
  page.once('dialog',dialog=>dialog.accept());
  await job.getByRole('button',{name:'Cancelar arte-000.png',exact:true}).click();
  await page.waitForFunction(id=>document.querySelector(`[data-job-id="${id}"] .st`).textContent==='cancelando',ready.first_id);
  const cancelled=await command('step');
  assert.equal(cancelled.active,99);assert(cancelled.archived_cancelled);
  await page.evaluate(()=>poll());await page.waitForFunction(()=>document.getElementById('ripCount').textContent==='99 / 100');
  await page.evaluate(()=>window.beforePreparation=document.querySelector('#jobs .job'));
  await command('prepare');await page.evaluate(()=>poll());
  await page.waitForFunction(()=>document.getElementById('ripCount').textContent==='100 / 100'&&document.getElementById('queuePreparing').textContent==='Preparando 1 arquivo…');
  assert(await page.evaluate(()=>beforePreparation===document.querySelector('#jobs .job')));
  await page.locator('#jobs').locator('..').screenshot({path:root+'/preparing.png'});
  await command('finish_prepare');await page.evaluate(()=>poll());
  await page.waitForFunction(()=>document.getElementById('ripCount').textContent==='99 / 100'&&document.getElementById('queuePreparing').textContent==='');
  await page.screenshot({path:root+'/desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  const geometry=await page.locator('#jobs').evaluate(e=>({height:e.clientHeight,scroll:e.scrollHeight}));
  assert(geometry.scroll>geometry.height&&geometry.height<=844*.65+14);
  await job.scrollIntoViewIfNeeded();await page.screenshot({path:root+'/mobile.png',fullPage:true});
  await page.setViewportSize({width:320,height:640});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  const normal=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'no-preference'});
  normal.on('pageerror',e=>errors.push(e.message));await normal.goto(ready.url);
  await normal.waitForFunction(()=>getComputedStyle(document.getElementById('intro')).visibility==='hidden');
  await normal.close();
  const cacheSize=await page.evaluate(()=>{const previous=first;first=true;for(let batch=0;batch<50;batch++){renderJobs(Array.from({length:12},(_,i)=>({id:`history-${batch}-${i}`,name:'Concluído',status:'pronto',progress:1})));}first=previous;return lastDone.size});
  assert.equal(cacheSize,12);assert.deepEqual(errors,[]);
  const report={passed:true,activeJobsShown:100,capacityBadge:'100 / 100',singleDomReplacement:true,
   idleDomPreserved:true,scrollPreserved:true,selectionPreserved:true,keyboardFocusPreserved:true,
   keyboardPauseResume:true,resumeQueuedItems:100,cancelPreservesArtwork:true,slotReleased:true,
   mobileGeometry:geometry,noOverflow390:true,noOverflow320:true,reducedMotionIntroHidden:true,
   reducedMotionAnimations:0,normalMotionIntroDismissed:true,completionCacheAfter600Jobs:cacheSize,
   fullUploadStatus:429,preparingSlotCounted:true,preparingHintShown:true,preparingDoesNotRebuildJobs:true,pageErrors:errors};
  fs.writeFileSync(root+'/browser-results.json',JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
 }finally{if(browser)await browser.close();if(service.exitCode===null&&service.signalCode===null){const exited=new Promise(resolve=>service.once('exit',resolve));service.stdin.end(JSON.stringify({operation:'stop'})+'\n');await exited}lines.close()}
})().catch(e=>{console.error(e);process.exit(1)});
