/** Browser regression for the Persona500 -> Card Studio image handoff.
 * Usage: node tools/verify_vibe_transfer.mjs /path/to/built-site /path/to/proof
 * The built site must contain studio/. No production requests or writes occur.
 */
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const site = path.resolve(process.argv[2] || '');
const proof = path.resolve(process.argv[3] || '');
if (!site || !proof || !fs.existsSync(path.join(site, 'studio', 'index.html'))) {
  throw new Error('Usage: node tools/verify_vibe_transfer.mjs /path/to/built-site /path/to/proof');
}
fs.mkdirSync(proof, { recursive: true });

const senderHtml = `<!doctype html><meta charset="utf-8"><title>isolated sender</title><script>
window.received=[]; window.studio=null; window.studioOrigin='';
addEventListener('message',e=>received.push({data:e.data,origin:e.origin,sourceIsStudio:e.source===studio}));
window.openStudio=url=>{studioOrigin=new URL(url).origin;studio=open(url,'_blank')};
window.sendV2=(id,src)=>studio.postMessage({vibeDrop:src,vibeTransfer:{version:2,id}},studioOrigin);
window.sendLegacy=src=>studio.postMessage({vibeDrop:src},studioOrigin);
window.makeImage=color=>{const c=document.createElement('canvas');c.width=8;c.height=8;const x=c.getContext('2d');x.fillStyle=color;x.fillRect(0,0,8,8);return c.toDataURL('image/png')};
<\/script>`;
const siblingHtml = `<!doctype html><meta charset="utf-8"><script>
window.received=[];addEventListener('message',e=>received.push(e.data));
window.attack=(id,src)=>opener.studio.postMessage({vibeDrop:src,vibeTransfer:{version:2,id}},opener.studioOrigin);
<\/script>`;

const mime = { '.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json','.png':'image/png','.svg':'image/svg+xml','.woff2':'font/woff2' };
function listen(handler) {
  return new Promise(resolve => { const server=http.createServer(handler); server.listen(0,'127.0.0.1',()=>resolve(server)); });
}
function close(server) { return new Promise(resolve=>server.close(resolve)); }
const staticServer = await listen((req,res)=>{
  const url=new URL(req.url,'http://127.0.0.1');
  let rel=decodeURIComponent(url.pathname).replace(/^\/+/, '');
  if (!rel || rel.endsWith('/')) rel += 'index.html';
  const file=path.resolve(site,rel);
  if (!file.startsWith(site+path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { res.writeHead(404);res.end('not found');return; }
  res.setHeader('content-type',mime[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));
});
const senderServer = await listen((req,res)=>{
  res.setHeader('content-type','text/html; charset=utf-8');
  res.end(new URL(req.url,'http://127.0.0.1').pathname==='/sibling' ? siblingHtml : senderHtml);
});
const studioOrigin=`http://127.0.0.1:${staticServer.address().port}`;
const senderOrigin=`http://127.0.0.1:${senderServer.address().port}`;
const report={schema:'vibe-transfer-browser-v1',started_at:new Date().toISOString(),studio_origin:studioOrigin,sender_origin:senderOrigin,checks:[],errors:[]};
const browser=await chromium.launch();

async function pair() {
  const context=await browser.newContext({viewport:{width:390,height:844}});
  await context.addInitScript(() => {
    const NativeImage=window.Image;
    const srcDescriptor=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src');
    const completeDescriptor=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'complete');
    window.__vibeTest={delayMs:0,failOnce:null,failed:[],draws:[]};
    window.Image=function(width,height){
      const img=new NativeImage(width,height);
      let assignmentPending=false;
      Object.defineProperty(img,'complete',{
        configurable:true,
        get(){return assignmentPending?false:completeDescriptor.get.call(img)}
      });
      Object.defineProperty(img,'src',{
        configurable:true,
        get(){return srcDescriptor.get.call(img)},
        set(value){
          const ctl=window.__vibeTest;
          if(ctl.failOnce===value&&!ctl.failed.includes(value)){
            ctl.failed.push(value);setTimeout(()=>img.dispatchEvent(new Event('error')),0);return;
          }
          const apply=()=>{assignmentPending=false;srcDescriptor.set.call(img,value)};
          if(ctl.delayMs&&String(value).startsWith('data:image/')){assignmentPending=true;setTimeout(apply,ctl.delayMs)}else apply();
        }
      });
      return img;
    };
    window.Image.prototype=NativeImage.prototype;
    const draw=CanvasRenderingContext2D.prototype.drawImage;
    CanvasRenderingContext2D.prototype.drawImage=function(image,...rest){
      if(image instanceof HTMLImageElement&&String(image.src).startsWith('data:image/'))window.__vibeTest.draws.push({src:image.src,connected:this.canvas.isConnected});
      return draw.call(this,image,...rest);
    };
  });
  const sender=await context.newPage();
  await sender.goto(senderOrigin,{waitUntil:'domcontentloaded'});
  const opened=context.waitForEvent('page');
  await sender.evaluate(url=>openStudio(url),studioOrigin+'/studio/');
  const studio=await opened;
  await studio.waitForLoadState('domcontentloaded');
  await studio.waitForFunction(()=>typeof S!=='undefined'&&S.doc&&document.querySelector('#canvas').width>0);
  return {context,sender,studio};
}
async function ack(sender,id,status){
  await sender.waitForFunction(([wanted,wantedStatus])=>received.some(x=>x.data&&x.data.transferId===wanted&&x.data.status===wantedStatus),[id,status]);
  return sender.evaluate(([wanted,wantedStatus])=>received.find(x=>x.data&&x.data.transferId===wanted&&x.data.status===wantedStatus),[id,status]);
}
async function image(sender,color){return sender.evaluate(c=>makeImage(c),color)}
async function check(name,fn){try{await fn();report.checks.push(name)}catch(error){report.errors.push({name,error:String(error.stack||error)});throw error}}

try {
  await check('received is nonterminal; placed follows connected-canvas draw',async()=>{
    const {context,sender,studio}=await pair();try{
      const src=await image(sender,'#df3048'),id='11111111111111111111111111111111';
      await studio.evaluate(()=>{__vibeTest.delayMs=350});
      await sender.evaluate(([i,s])=>sendV2(i,s),[id,src]);
      const got=await ack(sender,id,'received');assert.equal(got.sourceIsStudio,true);
      assert.equal(await studio.evaluate(()=>__vibeTest.draws.length),0);
      const placed=await ack(sender,id,'placed');assert.equal(placed.data.face,0);assert.equal(placed.data.placement,'blank');
      assert(await studio.evaluate(s=>__vibeTest.draws.some(d=>d.src===s&&d.connected),src));
      const count=await studio.evaluate(()=>S.doc.faces[0].elements.length);
      await sender.evaluate(([i,s])=>sendV2(i,s),[id,src]);
      await sender.waitForFunction(i=>received.filter(x=>x.data?.transferId===i&&x.data.status==='placed').length>=2,id);
      assert.equal(await studio.evaluate(()=>S.doc.faces[0].elements.length),count);
      const other=await image(sender,'#1155cc');
      await sender.evaluate(([i,s])=>sendV2(i,s),[id,other]);
      await sender.waitForFunction(i=>received.some(x=>x.data?.transferId===i&&x.data.reason==='id-reused'),id);
      assert.equal(await studio.evaluate(()=>S.doc.faces[0].elements.length),count);
    }finally{await context.close()}
  });

  await check('same-origin sibling cannot control receiver',async()=>{
    const {context,sender,studio}=await pair();try{
      const src=await image(sender,'#33aa55'),id='22222222222222222222222222222222';
      const opened=context.waitForEvent('page');await sender.evaluate(()=>window.sibling=open('/sibling','_blank'));const sibling=await opened;await sibling.waitForLoadState('domcontentloaded');
      await sibling.evaluate(([i,s])=>attack(i,s),[id,src]);await sibling.waitForTimeout(250);
      assert.deepEqual(await sibling.evaluate(()=>received),[]);
      assert.equal(await studio.evaluate(s=>S.doc.faces.some(f=>f.elements.some(e=>e.src===s)),src),false);
    }finally{await context.close()}
  });

  await check('newest transfer supersedes delayed predecessor',async()=>{
    const {context,sender,studio}=await pair();try{
      const a=await image(sender,'#8844cc'),b=await image(sender,'#00aacc');
      const aid='33333333333333333333333333333333',bid='44444444444444444444444444444444';
      await studio.evaluate(()=>{__vibeTest.delayMs=300});
      await sender.evaluate(([i,s])=>sendV2(i,s),[aid,a]);await ack(sender,aid,'received');
      await sender.evaluate(([i,s])=>sendV2(i,s),[bid,b]);
      const af=await ack(sender,aid,'failed');assert.equal(af.data.reason,'superseded');await ack(sender,bid,'placed');
      const sources=await studio.evaluate(()=>S.doc.faces[0].elements.map(e=>e.src));assert(sources.includes(b));assert(!sources.includes(a));
    }finally{await context.close()}
  });

  await check('user change during decode prevents mutation',async()=>{
    const {context,sender,studio}=await pair();try{
      const src=await image(sender,'#eeaa22'),id='55555555555555555555555555555555';
      await studio.evaluate(()=>{__vibeTest.delayMs=300});await sender.evaluate(([i,s])=>sendV2(i,s),[id,src]);await ack(sender,id,'received');
      await studio.click('#faceChip');const failed=await ack(sender,id,'failed');assert.equal(failed.data.reason,'design-changed');
      assert.equal(await studio.evaluate(s=>S.doc.faces.some(f=>f.elements.some(e=>e.src===s)),src),false);
    }finally{await context.close()}
  });

  await check('unsaved design is never overwritten',async()=>{
    const {context,sender,studio}=await pair();try{
      const src=await image(sender,'#331199'),id='66666666666666666666666666666666';
      await studio.evaluate(()=>{S.doc.name='My unsaved card';render()});
      await sender.evaluate(([i,s])=>sendV2(i,s),[id,src]);const failed=await ack(sender,id,'failed');assert.equal(failed.data.reason,'unsaved-design');
      assert.equal(await studio.evaluate(()=>S.doc.name),'My unsaved card');assert.equal(await studio.evaluate(s=>S.doc.faces.some(f=>f.elements.some(e=>e.src===s)),src),false);
    }finally{await context.close()}
  });

  await check('decode failure retains payload and Retry recovers locally',async()=>{
    const {context,sender,studio}=await pair();try{
      const src=await image(sender,'#008877'),id='77777777777777777777777777777777';
      await studio.evaluate(s=>{__vibeTest.failOnce=s},src);await sender.evaluate(([i,s])=>sendV2(i,s),[id,src]);
      const failed=await ack(sender,id,'failed');assert.equal(failed.data.reason,'decode-failed');
      assert.equal(await studio.locator('#vibeRetry').isVisible(),true);
      assert.match(await studio.locator('#handoffHelpText').textContent(),/Retry it, or refresh the page/);
      assert.equal(await studio.evaluate(s=>S.doc.faces.some(f=>f.elements.some(e=>e.src===s)),src),false);
      await studio.click('#vibeRetry');await studio.waitForFunction(s=>S.doc.faces.some(f=>f.elements.some(e=>e.src===s)),src);
      assert.equal(await studio.locator('#vibeRetry').isHidden(),true);
      assert(await studio.evaluate(s=>__vibeTest.draws.some(d=>d.src===s&&d.connected),src));
    }finally{await context.close()}
  });

  await check('new legacy intent makes an older Retry inert',async()=>{
    const {context,sender,studio}=await pair();try{
      const old=await image(sender,'#aa0066'),newer=await image(sender,'#0066aa');
      const id='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
      await studio.evaluate(s=>{__vibeTest.failOnce=s},old);
      await sender.evaluate(([i,s])=>sendV2(i,s),[id,old]);await ack(sender,id,'failed');
      assert.equal(await studio.locator('#vibeRetry').isVisible(),true);
      await sender.evaluate(s=>sendLegacy(s),newer);
      await studio.waitForFunction(s=>S.doc.faces[0].elements.some(e=>e.src===s),newer);
      assert.equal(await studio.locator('#vibeRetry').isHidden(),true);
      await studio.evaluate(()=>document.querySelector('#vibeRetry').click());await studio.waitForTimeout(100);
      const sources=await studio.evaluate(()=>S.doc.faces[0].elements.map(e=>e.src));
      assert(sources.includes(newer));assert(!sources.includes(old));
    }finally{await context.close()}
  });

  await check('assigned corrupt raster fails without waiting for timeout',async()=>{
    const {context,sender}=await pair();try{
      const id='cccccccccccccccccccccccccccccccc';
      const corrupt='data:image/png;base64,bm90LWEtcG5n';
      const began=Date.now();await sender.evaluate(([i,s])=>sendV2(i,s),[id,corrupt]);
      const failed=await ack(sender,id,'failed');assert.equal(failed.data.reason,'decode-failed');
      assert(Date.now()-began<3000);
    }finally{await context.close()}
  });

  await check('decode timeout releases queue and stale completion cannot place',async()=>{
    const {context,sender,studio}=await pair();try{
      const slow=await image(sender,'#bb3300'),next=await image(sender,'#00bb88');
      const slowId='88888888888888888888888888888888',nextId='99999999999999999999999999999999';
      await studio.evaluate(()=>{__vibeTest.delayMs=9000});
      await sender.evaluate(([i,s])=>sendV2(i,s),[slowId,slow]);
      const failed=await ack(sender,slowId,'failed');assert.equal(failed.data.reason,'decode-timeout');
      await studio.evaluate(()=>{__vibeTest.delayMs=0});
      await sender.evaluate(([i,s])=>sendV2(i,s),[nextId,next]);await ack(sender,nextId,'placed');
      await studio.waitForTimeout(1200);
      const sources=await studio.evaluate(()=>S.doc.faces[0].elements.map(e=>e.src));
      assert(sources.includes(next));assert(!sources.includes(slow));
    }finally{await context.close()}
  });

  await check('reload readiness permits an opener-held payload to recover',async()=>{
    const {context,sender,studio}=await pair();try{
      const src=await image(sender,'#cc7700'),id='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
      await studio.evaluate(s=>{__vibeTest.failOnce=s},src);
      await sender.evaluate(([i,s])=>sendV2(i,s),[id,src]);await ack(sender,id,'failed');
      const readyBefore=await sender.evaluate(()=>received.filter(x=>x.data?.vibeReady===1).length);
      await studio.reload({waitUntil:'domcontentloaded'});
      await studio.waitForFunction(()=>typeof S!=='undefined'&&S.doc&&document.querySelector('#canvas').width>0);
      await sender.waitForFunction(n=>received.filter(x=>x.data?.vibeReady===1).length>n,readyBefore);
      await sender.evaluate(([i,s])=>sendV2(i,s),[id,src]);await ack(sender,id,'placed');
      assert(await studio.evaluate(s=>S.doc.faces[0].elements.some(e=>e.src===s),src));
    }finally{await context.close()}
  });

  await check('legacy sender remains compatible and deduplicated',async()=>{
    const {context,sender,studio}=await pair();try{
      const src=await image(sender,'#222222');await sender.evaluate(s=>sendLegacy(s),src);
      await sender.waitForFunction(()=>received.some(x=>x.data?.vibeAck===1));
      await studio.waitForFunction(s=>S.doc.faces[0].elements.some(e=>e.src===s),src);
      const count=await studio.evaluate(()=>S.doc.faces[0].elements.length);
      await sender.evaluate(s=>sendLegacy(s),src);await sender.waitForTimeout(100);
      assert.equal(await studio.evaluate(()=>S.doc.faces[0].elements.length),count);
    }finally{await context.close()}
  });
} finally {
  report.finished_at=new Date().toISOString();
  report.passed=report.errors.length===0;
  report.app_sha256=crypto.createHash('sha256').update(fs.readFileSync(path.join(site,'studio','app.js'))).digest('hex');
  fs.writeFileSync(path.join(proof,'report.json'),JSON.stringify(report,null,2));
  await browser.close();await close(staticServer);await close(senderServer);
}
assert.equal(report.errors.length,0);
console.log(`PASS: ${report.checks.length} receiver scenarios; report ${path.join(proof,'report.json')}`);
