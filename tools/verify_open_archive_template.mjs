/** Real built-app regression: both faces, exact URL without chip identity, desktop/mobile, and actual PDF export. Author: Aldrin Payopay. Playwright is optional tooling, never an app dependency. */
import fs from 'node:fs'; import path from 'node:path'; import assert from 'node:assert/strict'; import crypto from 'node:crypto'; import {createRequire} from 'node:module'; import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url);
const {chromium,webkit}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const repo=fileURLToPath(new URL('../',import.meta.url));
const origin=process.argv[2],proof=process.argv[3];
if(!origin||!proof)throw Error('Usage: node tools/verify_open_archive_template.mjs http://127.0.0.1:PORT/ /path/to/scratch-proof (use an isolated test server; no printing or chip writes)');
assert(['127.0.0.1','localhost'].includes(new URL(origin).hostname),'Use an isolated loopback server');fs.mkdirSync(proof,{recursive:true});
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
(async()=>{
 const report=[];
 for(const [name,type]of Object.entries({chromium,webkit})){
  const browser=await type.launch(),context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[],forbidden=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>{
   const u=new URL(r.request().url());
   if(!['127.0.0.1','localhost'].includes(u.hostname)&&u.protocol.startsWith('http')){forbidden.push(u.href);return r.abort();}
   if(/^\/api\/(print|nfc(?:\/.*)?|enable-queue|reset-printer|printer|calibration|save-design|reveal)$/.test(u.pathname)){forbidden.push(u.pathname);return r.fulfill({status:403,body:'Not used by this test'});}
   if(u.pathname==='/api/pdf')return r.continue({postData:JSON.stringify({...JSON.parse(r.request().postData()),open:false})});
   return r.continue();
  });
  try{
   await page.goto(new URL('?template=pair%3Aopen-archive-front',origin).href);
   await page.waitForFunction(()=>typeof S!=='undefined'&&S.doc?.faces[0].elements[0]?.src==='cards/open-archive-front.png');await page.evaluate(()=>allImagesReady(S.doc));
   const state=await page.evaluate(()=>({card:S.doc.card,faces:S.doc.faces.map(f=>f.elements.map(e=>({src:e.src,w:e.w,h:e.h}))),origin:S.cardOrigin,tapReady:TEMPLATES['open-archive-front'].tapReady,options:[...document.querySelector('#templateSel').options].map(o=>({value:o.value,group:o.parentElement.label})),keys:Object.keys(TEMPLATES).sort(),nulTest:true}));
   assert.deepEqual(state.card,{w:85.6,h:53.98});assert.deepEqual(state.faces.map(f=>f[0].src),['cards/open-archive-front.png','cards/open-archive-back.png']);assert.equal(state.origin.url,'https://persona500.com/open-archive/');assert.equal(state.origin.epitaph,'');assert.equal(state.tapReady,false);
   assert(state.options.some(o=>o.value==='pair:open-archive-front'&&o.group==='Cards in the network'));
   assert(state.options.some(o=>o.value==='open-archive-back'&&o.group==='One face at a time'));
   for(const k of ['pair:run-this-game-front','pair:9am-sync-call-front'])assert(state.options.some(o=>o.value===k));
   await page.screenshot({path:path.join(proof,name+'-front.png'),fullPage:true});await page.click('[data-face="1"]');await page.screenshot({path:path.join(proof,name+'-back.png'),fullPage:true});
   await page.click('button[data-view="tray"]');await page.selectOption('#slotA','front');await page.selectOption('#slotB','back');await page.selectOption('#dpiSel','600');
   const profile=await page.evaluate(()=>({key:S.profileKey,page:S.profile.page_mm,slots:S.profile.slots,frame:S.frame,bleed:S.bleed}));
   await page.screenshot({path:path.join(proof,name+'-tray.png'),fullPage:true});
   const pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/pdf');await page.click('#btnPdf');const resp=await pending;assert.equal(resp.status(),200);const result=await resp.json();assert(fs.existsSync(result.pdf));const pdf=fs.readFileSync(result.pdf);assert.equal(pdf.subarray(0,4).toString(),'%PDF');
   fs.writeFileSync(path.join(proof,name+'-front-back-tray.pdf'),pdf);
   const mobile=[];await page.click('button[data-view="design"]');
   for(const width of [320,390]){
    await page.setViewportSize({width,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.click('#faceChip');await page.screenshot({path:path.join(proof,name+'-'+width+'.png'),fullPage:true});mobile.push({width,overflow:false,faceFlip:true});
   }
   assert.deepEqual(errors,[]);assert.deepEqual(forbidden,[]);
   report.push({engine:name,state,profile,pdfSha256:sha(pdf),pdfBytes:pdf.length,mobile,errors,forbidden});
  }finally{await context.close();await browser.close();}
 }
 const source=fs.readFileSync(path.join(repo,'src/web/app.js'));assert(source.includes(Buffer.from("'open-archive-front':")));
 fs.writeFileSync(path.join(proof,'browser-report.json'),JSON.stringify({records:report},null,2));console.log('PASS: actual paired template, both faces, real tray PDF export and320/390mobile in Chromium/WebKit; existing song pairs retained; no print/NFC/external requests.');
})().catch(e=>{console.error(e);process.exitCode=1});
