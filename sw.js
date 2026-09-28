/* Food Diary offline copy. Sits beside index.html.
   Opening the app: the live file is fetched and saved, so updates arrive as before. With no
   connection, or none within 4 seconds, the saved copy opens instead. The barcode reader for
   iPhone is saved too. Everything else (GitHub sync, the food list, Open Food Facts, update
   checks) goes straight to the network, as without this file. Only the diary's own page is
   handled: any other page in the same folder is left alone. */
const CACHE='food-diary-1';
const APP=new URL('./',self.location).href, PAGE=new URL('index.html',APP).href;
const ZX='https://cdn.jsdelivr.net/npm/@zxing/library@0.21.3/umd/index.min.js';
const plain=r=>new Response(r.body,{status:r.status,statusText:r.statusText,headers:r.headers});   // no redirect flag: iOS refuses to show a redirected copy
self.addEventListener('install',e=>{
  self.skipWaiting();
  e.waitUntil((async()=>{
    const c=await caches.open(CACHE);
    try{ const r=await fetch(PAGE,{cache:'reload'}); if(r.ok) await c.put(PAGE,plain(r)); }catch(x){}
    try{ await c.put(ZX,await fetch(ZX,{mode:'no-cors'})); }catch(x){}
  })());
});
self.addEventListener('activate',e=>e.waitUntil((async()=>{
  for(const k of await caches.keys()) if(k!==CACHE) await caches.delete(k);
  await self.clients.claim();
})()));
async function page(req){
  const c=await caches.open(CACHE), saved=await c.match(PAGE);
  const net=fetch(req.url,{cache:'no-cache',credentials:'same-origin'}).then(r=>{
    if(r.ok){ c.put(PAGE,plain(r.clone())); return r; }
    return saved||r;
  });
  if(!saved) return net;
  return Promise.race([net,new Promise(ok=>setTimeout(()=>ok(saved),4000))]).catch(()=>saved);
}
self.addEventListener('fetch',e=>{
  const req=e.request; if(req.method!=='GET') return;
  const u=new URL(req.url), bare=u.origin+u.pathname;
  if(req.mode==='navigate' && (bare===APP || bare===PAGE)) return e.respondWith(page(req));
  if(req.url===ZX) return e.respondWith(caches.match(ZX).then(r=>r||fetch(req).then(x=>{ const y=x.clone(); caches.open(CACHE).then(c=>c.put(ZX,y)); return x; })));
});
