// Seletores de arquivos e uploads HTTP reais em contextos móveis independentes.
const {chromium}=require(process.env.AUTORIP_PLAYWRIGHT_MODULE||'playwright');
const {spawn}=require('node:child_process');const {createInterface}=require('node:readline');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const output=process.argv[2]||fs.mkdtempSync(path.join(os.tmpdir(),'autorip-mobile-uploads-'));fs.mkdirSync(output,{recursive:true});
(async()=>{
 const child=spawn(process.env.AUTORIP_PYTHON||'python',[path.join(__dirname,'_queue_smoke_app.py'),'--upload-fixtures']);
 let browser,stderr='';child.stderr.on('data',data=>stderr+=data);const lines=createInterface({input:child.stdout});
 try{
  const ready=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error(stderr||'Harness timeout')),20000);lines.once('line',line=>{clearTimeout(timer);resolve(JSON.parse(line))})});
  browser=await chromium.launch({headless:true,executablePath:process.env.AUTORIP_CHROMIUM,args:process.env.AUTORIP_NO_SANDBOX==='1'?['--no-sandbox']:[]});
  const errors=[],requests=[];
  async function phone(){const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,reducedMotion:'reduce'});const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));page.setDefaultTimeout(10000);await page.goto(ready.url);await page.waitForFunction(()=>typeof openUpload==='function'&&typeof selectUploadFiles==='function');return page}
  const page=await phone();await page.waitForFunction(()=>document.querySelector('#connection').textContent.includes('conectado'));
  await page.locator('#openUpload').click();await page.locator('#pw').fill('senha-telefone');await page.locator('#pw2').fill('senha-telefone');await page.getByRole('button',{name:'Entrar',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#uploadDlg').open);
  page.on('request',request=>{if(new URL(request.url()).pathname==='/api/upload')requests.push(request.url())});
  const [chooser]=await Promise.all([page.waitForEvent('filechooser'),page.locator('#pickUploadFiles').click()]);assert(chooser.isMultiple());
  await chooser.setFiles([ready.upload_fixture,ready.upload_fixture.replace('.png','.tif')]);
  assert.equal(await page.locator('#uploadSelection li').count(),2);
  await page.locator('#uploadWidth').fill('301');await page.locator('#sendUpload').click();assert.equal(requests.length,0);
  await page.locator('#uploadWidth').fill('3');
  await page.evaluate(()=>{sendSelectedUploads();sendSelectedUploads()});
  await page.waitForFunction(()=>document.querySelector('#uploadStatus').textContent.includes('2 arquivo(s) enviado(s)'));
  assert.equal(requests.length,2);assert(requests.every(url=>new URL(url).searchParams.get('width')==='3'));
  assert.equal(await page.locator('#uploadProgress').evaluate(progress=>progress.value),1);
  await page.screenshot({path:path.join(output,'uploaded-mobile.png')});
  // Dois aparelhos adicionais fazem login e enviam artes de mesmo nome.
  const phones=await Promise.all([phone(),phone()]);
  await Promise.all(phones.map(async mobile=>{
   const response=await mobile.request.post(ready.url+'/api/login',{data:{password:'senha-telefone'}});assert.equal(response.status(),200);const {token}=await response.json();
   await mobile.evaluate(async value=>{stopPolling();token=value;await poll(true)},token);
   await mobile.locator('#openUpload').click();const [picker]=await Promise.all([mobile.waitForEvent('filechooser'),mobile.locator('#pickUploadPhotos').click()]);
   await picker.setFiles(ready.upload_fixture);await mobile.locator('#sendUpload').click();await mobile.waitForFunction(()=>document.querySelector('#uploadStatus').textContent.includes('1 arquivo(s) enviado(s)'));
  }));
  await page.evaluate(()=>poll(true));assert.equal(await page.locator('#jobs .job').count(),4);
  // Um erro preserva a sessão e a seleção, sem repetição automática do envio.
  await page.locator('#file').setInputFiles(ready.upload_fixture);
  await page.route('**/api/upload?*',route=>route.fulfill({status:429,json:{error:'Fila cheia; aguarde'}}));
  await page.locator('#sendUpload').click();await page.waitForFunction(()=>document.querySelector('#uploadStatus').textContent.includes('Fila cheia'));
  assert.equal(await page.locator('#uploadSelection li').count(),1);assert(await page.evaluate(()=>Boolean(token)));
  await page.unroute('**/api/upload?*');
  const delayed=[];await page.route('**/api/upload?*',route=>{delayed.push(route)});
  await page.locator('#sendUpload').click();await page.waitForFunction(()=>uploadRunning);
  await page.evaluate(()=>lockPanel());await page.waitForFunction(()=>apiRequests.size===0);
  assert.equal(await page.locator('#uploadSelection li').count(),0);assert(!(await page.locator('#uploadDlg').evaluate(dialog=>dialog.open)));
  for(const route of delayed)await route.abort().catch(()=>{});
  assert.deepEqual(errors,[]);
  const report={passed:true,mobileContexts:3,actualUploads:4,multipleFileChooser:true,galleryChooser:true,widthValidated:true,
   doubleTapDoesNotDuplicate:true,progressShown:true,loginResumesUploadDialog:true,queueErrorKeepsSelectionAndSession:true,
   logoutAbortsTransferAndClearsSelection:true,sameFilenameFromDifferentPhones:true,physicalPhonesTested:false,pageErrors:errors};
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
 }finally{if(browser)await browser.close();if(child.exitCode===null){const stopped=new Promise(resolve=>child.once('exit',resolve));child.stdin.end(JSON.stringify({operation:'stop'})+'\n');await stopped}lines.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
