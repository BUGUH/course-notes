const toc = document.querySelector('.toc details');
if (toc && matchMedia('(max-width:850px)').matches) toc.open = false;
const tocLinks = [...document.querySelectorAll('.toc a')];
for (const a of tocLinks) a.addEventListener('click', () => {
  if (!toc || !matchMedia('(max-width:850px)').matches) return;
  toc.open = false;
  requestAnimationFrame(() => document.getElementById(decodeURIComponent(a.hash.slice(1)))?.scrollIntoView({block:'start'}));
});
function highlight(id) {
  for (const a of tocLinks) {
    if (decodeURIComponent(a.hash.slice(1)) === id) a.setAttribute('aria-current','location');
    else a.removeAttribute('aria-current');
  }
}
const doc = document.querySelector('.facsimile');
if (!doc) {
  const headings = [...document.querySelectorAll('.prose :is(h2,h3,h4,h5,h6)[id], .prose section[id], #downloads')];
  const watch = new IntersectionObserver(entries => {
    for (const entry of entries) if (entry.isIntersecting) highlight(entry.target.id);
  },{rootMargin:'0px 0px -70% 0px'});
  headings.forEach(h => watch.observe(h));
} else {
  showOriginal(doc).catch(() => {
    const status = document.getElementById('reader-status');
    status.hidden = false;
    status.textContent = '当前浏览器无法显示原页，请用上方的「打开 PDF」阅读。';
  });
}
async function showOriginal(host) {
  const count = Number(host.dataset.pages);
  const first = Number(host.dataset.startPage || 1);
  const last = Number(host.dataset.endPage || count);
  if (!Number.isInteger(first) || !Number.isInteger(last) || first < 1 || last > count || first > last) throw Error('Invalid chapter range');
  const stack = document.getElementById('sheets');
  const number = document.getElementById('page-number');
  const status = document.getElementById('reader-status');
  const pages = [];
  const holders = document.createDocumentFragment();
  for (let n=first;n<=last;n++) {
    const el=document.createElement('div');
    el.className='sheet'; el.id='page-'+n; el.dataset.n=n;
    el.setAttribute('role','img');el.setAttribute('aria-label','第 '+n+' 页原文');
    el.style.aspectRatio=host.dataset.ratio;
    holders.append(el); pages.push(el);
  }
  stack.append(holders);
  function go(n) {
    if (!Number.isInteger(n)||n<first||n>last) {number.value=String(first);return;}
    const page=pages[n-first];
    page.scrollIntoView({block:'start'});
    history.replaceState(null,'','#'+page.id);
    number.value=String(n);
  }
  number.addEventListener('change',()=>go(Number(number.value)));
  number.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();go(Number(number.value));}});
  if (/^#page-\d+$/.test(location.hash)) go(Number(location.hash.slice(6)));
  const pdfjs=await import('./pdfjs/build/pdf.min.mjs');
  pdfjs.GlobalWorkerOptions.workerSrc=new URL('./pdfjs/build/pdf.worker.min.mjs',import.meta.url).href;
  const base=new URL('./pdfjs/',import.meta.url);
  const pdf=await pdfjs.getDocument({
    url:host.dataset.url,cMapUrl:new URL('cmaps/',base).href,cMapPacked:true,
    standardFontDataUrl:new URL('standard_fonts/',base).href,wasmUrl:new URL('wasm/',base).href,
    iccUrl:new URL('iccs/',base).href,isEvalSupported:false,enableXfa:false
  }).promise;
  if (pdf.numPages!==count) throw Error('Page count mismatch');
  const jobs=new Map();const visible=new Set();
  const queue=new Set();
  let active=0;
  function pump() {
    while(active<2 && queue.size) {
      const [el]=queue;queue.delete(el);
      if (!visible.has(el)||jobs.has(el))continue;
      active++; const record={};jobs.set(el,record);
      draw(el,record).catch(err=>{
        if (err?.name!=='RenderingCancelledException' && visible.has(el)) {
          status.hidden=false;status.textContent='有原页未能显示，可用「打开 PDF」查看。';
        }
      }).finally(()=>{active--;pump();});
    }
  }
  async function draw(el,record) {
    const sheet=await pdf.getPage(Number(el.dataset.n));
    if(!visible.has(el)||jobs.get(el)!==record)return;
    const v=sheet.getViewport({scale:1});
    const pixels=Math.min(2,window.devicePixelRatio||1);
    const scale=Math.min(2250/v.width,Math.max(1,el.clientWidth)*pixels/v.width);
    const viewport=sheet.getViewport({scale});
    el.style.aspectRatio=v.width+'/'+v.height;
    const canvas=document.createElement('canvas');
    canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);
    canvas.setAttribute('aria-hidden','true');el.replaceChildren(canvas);
    record.task=sheet.render({canvas,canvasContext:canvas.getContext('2d',{alpha:false}),viewport});
    await record.task.promise;
    status.hidden=true;
  }
  const nearby=new IntersectionObserver(entries=>{
    for(const item of entries) {
      const el=item.target;
      if(item.isIntersecting){visible.add(el);if(!jobs.has(el))queue.add(el);}
      else{
        visible.delete(el);queue.delete(el);
        const r=jobs.get(el); if(r?.task)r.task.cancel();
        jobs.delete(el); el.replaceChildren();
      }
    }
    pump();
  },{rootMargin:'80% 0px'});
  const current=new IntersectionObserver(entries=>{
    for(const item of entries)if(item.isIntersecting){
      const page=Number(item.target.dataset.n);
      if(document.activeElement!==number)number.value=String(page);
      const label=[...tocLinks].reverse().find(a=>a.hash.startsWith('#page-')&&Number(a.hash.slice(6))<=page);
      if(label)highlight(label.hash.slice(1));
    }
  },{rootMargin:'0px 0px -65% 0px'});
  for(const el of pages){nearby.observe(el);current.observe(el);}
}
