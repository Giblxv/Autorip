// Planejador real, arquivos temporários e respostas controladas para as corridas.
const {chromium}=require(process.env.AUTORIP_PLAYWRIGHT_MODULE||'playwright');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const output=process.argv[2]||fs.mkdtempSync(path.join(os.tmpdir(),'autorip-nesting-ui-'));fs.mkdirSync(output,{recursive:true});
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve}};
(async()=>{
 const child=spawn(process.env.AUTORIP_PYTHON||'python',[path.join(__dirname,'_queue_smoke_app.py'),'--polling-fixtures']);
 let stderr='',browser;child.stderr.on('data',d=>stderr+=d);
 const ready=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error(stderr)),20000);createInterface({input:child.stdout}).once('line',line=>{clearTimeout(timer);resolve(JSON.parse(line))})});
 const results=[];
 try{
  browser=await chromium.launch({headless:true,...(process.env.AUTORIP_CHROMIUM?{executablePath:process.env.AUTORIP_CHROMIUM}:{}),args:process.env.AUTORIP_NO_SANDBOX==='1'?['--no-sandbox']:[]});
  async function test(name,fn,viewport={width:1440,height:1000},authenticated=true){
   const page=await browser.newPage({viewport,reducedMotion:'reduce',acceptDownloads:true}),errors=[];page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(10000);
   try{
    await page.addInitScript(()=>{const create=URL.createObjectURL,revoke=URL.revokeObjectURL;window.activeSVG=new Set();URL.createObjectURL=blob=>{const url=create(blob);if(blob.type==='image/svg+xml')activeSVG.add(url);return url};URL.revokeObjectURL=url=>{activeSVG.delete(url);revoke(url)}});
    await page.goto(ready.url);if(authenticated)await page.evaluate(async()=>{token='queue-browser-token';await poll(true)});
    await page.locator('#openSheet').click();
    if(authenticated)await page.waitForFunction(()=>document.querySelectorAll('#sheetSources tr').length===2);
    await fn(page);assert.deepEqual(errors,[]);results.push({name,passed:true});
   }catch(e){results.push({name,passed:false,error:e.message,pageErrors:errors});await page.screenshot({path:path.join(output,name.replace(/\W/g,'-')+'-failure.png')}).catch(()=>{})}
   finally{await page.close()}
  }
  async function select(page,count=1){
   const rows=page.locator('#sheetSources tr');for(let i=0;i<count;i++){await rows.nth(i).locator('input[type=checkbox]').check();await rows.nth(i).locator('.sheet-width').fill('12')}
  }
  async function compute(page){await page.locator('#sheetCompute').click();await page.waitForFunction(()=>sheetPlan!==null);await page.waitForFunction(()=>document.querySelector('#sheetPreview').naturalWidth>0)}
  async function hold(page){const started=deferred(),release=deferred();await page.route('**/api/layout/plan',async route=>{const response=await route.fetch();started.resolve();await release.promise;await route.fulfill({response})});return{started,release}}
  await test('desktop preview and exports',async page=>{
   await select(page,2);await page.locator('.sheet-quantity').first().fill('3');await compute(page);
   assert((await page.locator('#sheetSummary').innerText()).includes('4 peças'));
   assert.equal(await page.evaluate(async()=>(await api('/api/state')).d.queue_used),100);
   const jsonEvent=page.waitForEvent('download');await page.locator('#sheetJson').click();const json=JSON.parse(fs.readFileSync(await(await jsonEvent).path(),'utf8'));
   assert.equal(json.items.length,4);assert(json.items.every(i=>i.path===''));assert(json.utilization>0&&json.utilization<=1);
   const svgEvent=page.waitForEvent('download');await page.locator('#sheetSvg').click();assert(fs.readFileSync(await(await svgEvent).path(),'utf8').includes('<svg'));
   await page.screenshot({path:path.join(output,'desktop.png')});
   await page.locator('#sheetMargin').fill('1');assert(await page.locator('#sheetPreview').isHidden());assert.equal(await page.evaluate(()=>activeSVG.size),0);
  });
  await test('edit while calculation pending',async page=>{
   await select(page);const barrier=await hold(page);await page.locator('#sheetCompute').click();await barrier.started.promise;
   await page.locator('.sheet-width').first().fill('15');barrier.release.resolve();await page.waitForFunction(()=>!sheetComputing);
   assert.equal(await page.evaluate(()=>sheetPlan),null);assert(await page.locator('#sheetPreview').isHidden());
  });
  await test('close while calculation pending',async page=>{
   await select(page);const barrier=await hold(page);await page.locator('#sheetCompute').click();await barrier.started.promise;
   await page.evaluate(()=>document.getElementById('sheetDlg').close());barrier.release.resolve();await page.waitForFunction(()=>!sheetComputing);
   assert.equal(await page.evaluate(()=>sheetPlan),null);assert.equal(await page.evaluate(()=>activeSVG.size),0);
  });
  await test('session change discards private planning',async page=>{
   await select(page);const barrier=await hold(page);await page.locator('#sheetCompute').click();await barrier.started.promise;
   await page.evaluate(()=>{lockPanel();token='queue-browser-token-new'});barrier.release.resolve();await page.waitForFunction(()=>apiRequests.size===0);
   assert.equal(await page.evaluate(()=>sheetPlan),null);assert.equal(await page.locator('#sheetSources tr').count(),0);assert.equal(await page.evaluate(()=>token),'queue-browser-token-new');
  });
  await test('piece capacity error preserves login',async page=>{
   await select(page,2);for(const input of await page.locator('.sheet-quantity').all())await input.fill('60');
   await page.locator('#sheetCompute').click();await page.waitForFunction(()=>!sheetComputing);
   assert((await page.locator('#sheetMessage').innerText()).includes('100 peças'));assert.equal(await page.evaluate(()=>token),'queue-browser-token');
  });
  await test('removed source reports error',async page=>{
   await select(page);await page.route('**/api/layout/plan',r=>r.fulfill({status:404,json:{error:'A arte saiu da hot folder; atualize.'}}));
   await page.locator('#sheetCompute').click();await page.waitForFunction(()=>!sheetComputing);
   assert((await page.locator('#sheetMessage').innerText()).includes('atualize'));assert.equal(await page.evaluate(()=>token),'queue-browser-token');
  });
  for(const width of [390,320])await test('mobile '+width,async page=>{
   await select(page);await compute(page);
   assert(await page.evaluate(()=>document.getElementById('sheetDlg').getBoundingClientRect().width<=innerWidth));
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.screenshot({path:path.join(output,'mobile-'+width+'.png')});
  },{width,height:844});
  await test('login required to open planner',async page=>{
   assert(await page.locator('#dlg').evaluate(e=>e.open));assert(!await page.locator('#sheetDlg').evaluate(e=>e.open));
  },{width:1440,height:1000},false);
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({results},null,2));
  console.log(JSON.stringify({passed:results.filter(r=>r.passed).length,total:results.length,results,output}));
  if(results.some(r=>!r.passed))process.exitCode=1;
 }finally{if(browser)await browser.close();child.stdin.end(JSON.stringify({operation:'stop'})+'\n')}
})().catch(e=>{console.error(e);process.exitCode=1});
