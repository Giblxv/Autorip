// Controlled 100-job progress updates. Fresh Chromium process for each side/trial.
const {chromium}=require(process.env.AUTORIP_PLAYWRIGHT_MODULE||'playwright');
const {spawn,execFileSync}=require('node:child_process');
const {createInterface}=require('node:readline');
const {parseArgs}=require('node:util');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const assert=require('node:assert/strict');
const root=path.join(__dirname,'..');
const {values:args}=parseArgs({options:{
 'baseline-ref':{type:'string'},output:{type:'string'},repeat:{type:'string',default:'3'},
 updates:{type:'string',default:'50'},seed:{type:'string',default:'20261111'},aa:{type:'boolean',default:false}
}});
assert(args['baseline-ref']&&args.output,'--baseline-ref and --output required');
const repeats=Number(args.repeat),updates=Number(args.updates);
assert(Number.isInteger(repeats)&&repeats>=3&&Number.isInteger(updates)&&updates>=20);
const sha=data=>crypto.createHash('sha256').update(data).digest('hex');
const baselineRef=execFileSync('git',['rev-parse',args['baseline-ref']],{cwd:root,encoding:'utf8'}).trim();
const before=execFileSync('git',['show',baselineRef+':autorip/ui/index.html'],{cwd:root,encoding:'utf8'});
const currentPath=path.join(root,'autorip/ui/index.html'),current=fs.readFileSync(currentPath,'utf8');
const scripts=[before,args.aa?before:current];
let randomState=Number(args.seed)>>>0;
const random=()=>((randomState=(Math.imul(randomState,1664525)+1013904223)>>>0)/4294967296);
const median=items=>{const sorted=items.slice().sort((a,b)=>a-b),n=sorted.length;return n%2?sorted[n>>1]:(sorted[n/2-1]+sorted[n/2])/2};
(async()=>{
 const child=spawn(process.env.AUTORIP_PYTHON||'python',[path.join(root,'tools/_queue_smoke_app.py'),'--polling-fixtures']);
 let stderr='';child.stderr.on('data',data=>stderr+=data);
 const lines=createInterface({input:child.stdout});
 let browser;
 try{
  const ready=await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(new Error(stderr||'Harness timeout')),20000);lines.once('line',line=>{clearTimeout(timeout);resolve(JSON.parse(line))})});
  const report={baselineRef,repeats,updates,seed:Number(args.seed),aaControl:args.aa,
   scope:'Synchronous renderJobs plus forced layout; 100 synthetic cards without thumbnails, first 5 updates warmup; import/navigation/authentication excluded',
   sampling:'Fresh Chromium process per side/trial; randomized paired order; every measured update retained',
   limits:'Desktop Chromium and mobile viewport, not native Android/iOS hardware, battery or whole application latency',
   uiSha256:scripts.map(sha),benchmarkSha256:sha(fs.readFileSync(__filename)),scenarios:{}};
  for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
   const groups=[[],[]];let oracle=null;
   for(let trial=0;trial<repeats;trial++){
    const order=random()<.5?[0,1]:[1,0];
    for(const side of order){
     browser=await chromium.launch({headless:true,...(process.env.AUTORIP_CHROMIUM?{executablePath:process.env.AUTORIP_CHROMIUM}:{}),args:process.env.AUTORIP_NO_SANDBOX==='1'?['--no-sandbox']:[]});
     report.browser=browser.version();
     const page=await browser.newPage({viewport,reducedMotion:'reduce'}),errors=[];
     page.on('pageerror',error=>errors.push(error.message));
     await page.route(ready.url+'/',route=>route.fulfill({contentType:'text/html',body:scripts[side]}));
     await page.addInitScript(()=>{const original=window.setInterval;window.__timers=[];window.setInterval=(...args)=>{const id=original(...args);__timers.push(id);return id}});
     await page.goto(ready.url);
     await page.evaluate(async()=>{for(const id of __timers)clearInterval(id);token='queue-browser-token';await Promise.all([poll(true),pollPrints(true),pollHotFiles(true)]);await poll(true)});
     const sample=await page.evaluate(count=>{
      const jobs=Array.from({length:100},(_,i)=>({id:'bench-'+i,name:'arte-'+i+'.png',status:i===0?'processando':'fila',progress:0}));
      const box=document.querySelector('#jobs');
      for(let i=0;i<5;i++){jobs[0].progress=i/100;renderJobs(jobs);void box.offsetHeight}
      const milliseconds=[];
      for(let i=0;i<count;i++){jobs[0].progress=(i+1)/(count+1);const start=performance.now();renderJobs(jobs);void box.offsetHeight;milliseconds.push(performance.now()-start)}
      return{milliseconds,dom:box.innerHTML,cards:box.querySelectorAll('.job').length};
     },updates);
     assert.deepEqual(errors,[]);assert.equal(sample.cards,100);
     sample.domSha256=sha(sample.dom);delete sample.dom;
     if(oracle===null)oracle=sample.domSha256;
     assert.equal(sample.domSha256,oracle,'Rendered output differs');
     sample.trial=trial;sample.order=order;sample.medianMilliseconds=median(sample.milliseconds);groups[side].push(sample);
     await browser.close();browser=null;
    }
   }
   const medians=groups.map(group=>median(group.map(sample=>sample.medianMilliseconds)));
   report.scenarios[name]={viewport,medianMilliseconds:medians,speedup:medians[0]/medians[1],domSha256:oracle,samples:groups};
   console.log(JSON.stringify({scenario:name,medianMilliseconds:medians,speedup:medians[0]/medians[1]}));
   fs.mkdirSync(path.dirname(path.resolve(args.output)),{recursive:true});fs.writeFileSync(args.output,JSON.stringify(report,null,2)+'\n');
  }
  assert.equal(sha(fs.readFileSync(currentPath,'utf8')),sha(current),'UI changed while measuring');
  assert.equal(sha(fs.readFileSync(__filename)),report.benchmarkSha256,'Benchmark changed while measuring');
  report.complete=true;fs.writeFileSync(args.output,JSON.stringify(report,null,2)+'\n');
 }finally{
  if(browser)await browser.close();
  if(child.exitCode===null&&child.signalCode===null){const exited=new Promise(resolve=>child.once('exit',resolve));child.stdin.end(JSON.stringify({operation:'stop'})+'\n');await exited}
  lines.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1});
