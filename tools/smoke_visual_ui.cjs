// Real HTTP panel, responsive dialogs, reduced motion and mobile connection UI.
// Uses the same optional Playwright/Chromium environment as smoke_queue_ui.cjs.
const {chromium}=require(process.env.AUTORIP_PLAYWRIGHT_MODULE||'playwright');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const output=process.argv[2]||fs.mkdtempSync(path.join(os.tmpdir(),'autorip-visual-ui-'));
fs.mkdirSync(output,{recursive:true});
(async()=>{
 const child=spawn(process.env.AUTORIP_PYTHON||'python',[path.join(__dirname,'_queue_smoke_app.py'),'--polling-fixtures']);
 let stderr='',browser;child.stderr.on('data',data=>stderr+=data);
 const lines=createInterface({input:child.stdout});
 try{
  const ready=await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(new Error(stderr||'Harness timeout')),20000);lines.once('line',line=>{clearTimeout(timeout);resolve(JSON.parse(line))})});
  browser=await chromium.launch({headless:true,...(process.env.AUTORIP_CHROMIUM?{executablePath:process.env.AUTORIP_CHROMIUM}:{}),args:process.env.AUTORIP_NO_SANDBOX==='1'?['--no-sandbox']:[]});
  const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'}),errors=[],missing=[];
  page.on('pageerror',error=>errors.push(error.message));page.on('response',response=>{if(response.status()===404)missing.push(response.url())});
  page.setDefaultTimeout(10000);
  await page.goto(ready.url);
  await page.evaluate(async()=>{token='queue-browser-token';await Promise.all([poll(true),pollPrints(true),pollHotFiles(true)]);dlg.close()});
  await page.waitForFunction(()=>document.querySelectorAll('#jobs .job').length===100);
  assert.equal(await page.locator('.card').first().evaluate(element=>getComputedStyle(element).backgroundColor),'rgb(24, 14, 46)');
  assert(await page.locator('.brand-mark').evaluate(image=>image.complete&&image.naturalWidth===256));
  assert.equal(await page.evaluate(()=>document.getAnimations().length),0);
  const widths=[1440,768,390,320];
  for(const width of widths){
   await page.setViewportSize({width,height:1000});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Panel overflow at ${width}`);
   await page.screenshot({path:path.join(output,`panel-${width}.png`)});
   await page.getByRole('button',{name:'⚙ Configurações',exact:true}).click();
   await page.waitForFunction(()=>document.getElementById('cfgBox').style.display!=='none');
   assert(await page.locator('#dlg').evaluate(element=>element.scrollWidth<=element.clientWidth),`Settings overflow at ${width}`);
   await page.locator('#dlg').screenshot({path:path.join(output,`settings-${width}.png`)});
   await page.evaluate(()=>dlg.close());
   await page.locator('#openSheet').click();
   await page.waitForFunction(()=>document.querySelectorAll('#sheetSources tr').length===2);
   assert(await page.locator('#sheetDlg').evaluate(element=>element.scrollWidth<=element.clientWidth),`Planner overflow at ${width}`);
   await page.locator('#sheetDlg').screenshot({path:path.join(output,`planner-${width}.png`)});
   await page.evaluate(()=>sheetDlg.close());
  }
  await page.setViewportSize({width:1440,height:1000});
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.evaluate(()=>{renderJobs([{id:'active',name:'active.png',status:'processando',progress:.42},{id:'done',name:'done.png',status:'pronto',progress:1}]);first=false});
  const active=page.locator('.job[data-status=processando] .fill');
  assert.equal(await active.evaluate(element=>getComputedStyle(element,'::before').animationName),'progressFlow');
  assert.equal(await page.locator('.job[data-status=pronto] .fill').evaluate(element=>getComputedStyle(element,'::before').animationName),'none');
  await page.evaluate(()=>document.body.classList.add('tab-hidden'));
  assert.equal(await active.evaluate(element=>getComputedStyle(element,'::before').animationPlayState),'paused');
  await page.evaluate(()=>document.body.classList.remove('tab-hidden'));
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await page.evaluate(()=>document.getAnimations().length),0);
  // Serve the actual packaged Android landing page and bundle, not a mock app.
  const mobile=await browser.newPage({viewport:{width:390,height:844}});
  mobile.on('pageerror',error=>errors.push(error.message));
  await mobile.route('**/mobile-preview/',route=>route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(__dirname,'../mobile/public/index.html'))}));
  await mobile.route('**/mobile-preview/app.js',route=>route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(__dirname,'../mobile/public/app.js'))}));
  await mobile.route('**/mobile-preview/brand-mark.png',route=>route.fulfill({contentType:'image/png',body:fs.readFileSync(path.join(__dirname,'../mobile/public/brand-mark.png'))}));
  await mobile.goto(ready.url+'/mobile-preview/');
  for(const width of [390,320]){
   await mobile.setViewportSize({width,height:844});
   assert(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Mobile overflow at ${width}`);
   await mobile.locator('#url').fill('http://host/?token=private');await mobile.locator('#connect').click();
   assert((await mobile.locator('#error').innerText()).includes('sem usuário, senha'));
   await mobile.screenshot({path:path.join(output,`mobile-${width}.png`)});
  }
  await mobile.locator('#url').fill(ready.url);await mobile.locator('#connect').click();
  await mobile.waitForURL(ready.url+'/');
  assert.deepEqual(errors,[]);assert.deepEqual(missing,[]);
  const report={passed:true,widths,noPanelOrDialogOverflow:true,reducedMotionAnimations:0,hiddenProgressPaused:true,completedProgressStatic:true,mobileConnectionPreserved:true,missingAssets:missing,pageErrors:errors};
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
 }finally{
  if(browser)await browser.close();
  if(child.exitCode===null){const stopped=new Promise(resolve=>child.once('exit',resolve));child.stdin.end(JSON.stringify({operation:'stop'})+'\n');await stopped}
  lines.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1});
