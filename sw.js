/* Food Diary offline copy. Sits beside index.html.
   Opening the app shows the copy saved on the phone straight away, so there's no wait on the
   network (the black screen). The live file is fetched at the same time and saved for next time;
   the app's own update check then reloads onto a newer version, and that reload (index.html?v=…)
   asks the network first. The very first open, with nothing saved yet, comes from the network.
   The barcode reader for iPhone is saved too. Everything else (GitHub sync, the food list, Open
   Food Facts, update checks) goes straight to the network. Any other page in the folder is left alone. */
const CACHE='food-diary-2';
const APP=new URL('./',self.location).href, PAGE=new URL('index.html',APP).href;
const ZX='https://cdn.jsdelivr.net/npm/@zxing/library@0.21.3/umd/index.min.js';
const plain=r=>new Response(r.body,{status:r.status,statusText:r.statusText,headers:r.headers});   // no redirect flag: iOS refuses to show a redirected copy
self.addEventListener('install',e=>{
  self.skipWaiting();
  e.waitUntil((async()=>{
    const c=await caches.open(CACHE), old=await caches.match(PAGE);   // an earlier offline copy carries over until the fresh one lands
    if(old) await c.put(PAGE,old.clone());
    try{ const r=await fetch(PAGE,{cache:'reload'}); if(r.ok) await c.put(PAGE,plain(r)); }catch(x){}
    try{ const z=await caches.match(ZX); await c.put(ZX,z||await fetch(ZX,{mode:'no-cors'})); }catch(x){}
  })());
});
self.addEventListener('activate',e=>e.waitUntil((async()=>{
  for(const k of await caches.keys()) if(k!==CACHE) await caches.delete(k);
  await self.clients.claim();
})()));
/* The page: {res} is what opens, {done} is the saving of the fresh copy, which runs on after. */
async function page(req,update){
  const c=await caches.open(CACHE), saved=await c.match(PAGE);
  const net=fetch(req.url,{cache:'no-cache',credentials:'same-origin'}).then(async r=>{ if(r.ok) await c.put(PAGE,plain(r.clone())); return r; });
  if(!saved) return {res:net, done:net.catch(()=>{})};
  if(!update){ return {res:saved, done:net.catch(()=>{})}; }          // opening: the saved copy at once
  const res=Promise.race([net.then(r=>r.ok?r:saved),new Promise(ok=>setTimeout(()=>ok(saved),4000))]).catch(()=>saved);   // an update: fresh if it comes
  return {res, done:net.catch(()=>{})};
}
self.addEventListener('fetch',e=>{
  const req=e.request; if(req.method!=='GET') return;
  const u=new URL(req.url), bare=u.origin+u.pathname;
  if(req.mode==='navigate' && (bare===APP || bare===PAGE)){
    const p=page(req,u.searchParams.has('v'));
    e.respondWith(p.then(x=>x.res)); e.waitUntil(p.then(x=>x.done)); return;
  }
  if(req.url===ZX) return e.respondWith(caches.match(ZX).then(r=>r||fetch(req).then(x=>{ const y=x.clone(); caches.open(CACHE).then(c=>c.put(ZX,y)); return x; })));
});
