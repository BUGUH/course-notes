
'use strict';
const get = id => document.getElementById(id);
const rows = [...document.querySelectorAll('.entry')];
const reviewing = !!get('export');
const decisions = Object.create(null);
const storageKey = 'course-note-choices-v2';
if (reviewing) {
  try { Object.assign(decisions, JSON.parse(localStorage.getItem(storageKey) || '{}')); } catch {}
  for (const row of rows) {
    const choice = row.querySelector('.decision');
    const prior=decisions[row.dataset.id] ?? decisions[row.dataset.oldid] ?? row.dataset.initial; if (['yes','no'].includes(prior)) choice.value = prior;
    choice.addEventListener('change', () => {
      decisions[row.dataset.id] = choice.value;
      try { localStorage.setItem(storageKey, JSON.stringify(decisions)); } catch { get('storage').textContent='此浏览器未能保存选择，请导出清单。'; }
      update();
    });
  }
  get('export').addEventListener('click', () => {
    const items = rows.map(row => ({id:row.dataset.id, title:row.querySelector('.title').textContent, course:row.dataset.course, decision:row.querySelector('.decision').value}));
    const url = URL.createObjectURL(new Blob([JSON.stringify({schema:1,items},null,2)],{type:'application/json;charset=utf-8'}));
    const a=document.createElement('a'); a.href=url; a.download='博客公开选择.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  get('import').addEventListener('change',async event=>{
    const file=event.target.files[0]; if(!file)return;
    try {const v=JSON.parse(await file.text());if(v.schema!==1||!Array.isArray(v.items)||!v.items.every(i=>i&&typeof i.id==='string'&&['pending','yes','no'].includes(i.decision)))throw Error();
      const byId=new Map(v.items.map(i=>[i.id,i.decision]));
      for(const row of rows){if(byId.has(row.dataset.id)||byId.has(row.dataset.oldid)){const s=row.querySelector('.decision');s.value=byId.get(row.dataset.id)??byId.get(row.dataset.oldid);decisions[row.dataset.id]=s.value;}}
      try{localStorage.setItem(storageKey,JSON.stringify(decisions));}catch{} update();get('storage').textContent='已读入选择。';
    }catch{get('storage').textContent='未能读取这份选择清单。';}event.target.value='';
  });
}
function update() {
 const q=get('q').value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
 let visible=0,yes=0,no=0;
 for(const row of rows){const match=(!get('course').value||get('course').value===row.dataset.course)&&(!get('fmt').value||get('fmt').value===row.dataset.fmt)&&q.every(word=>row.dataset.search.includes(word));row.hidden=!match;if(match)visible++;
  if(reviewing){const decision=row.querySelector('.decision').value;if(decision==='yes')yes++;if(decision==='no')no++;}}
 for(const group of document.querySelectorAll('.course'))group.hidden=![...group.querySelectorAll('.entry')].some(r=>!r.hidden);
 get('count').textContent='当前显示 '+visible+' 份'+(reviewing?' · 选定公开 '+yes+' 份 · 不公开 '+no+' 份 · 待确认 '+(rows.length-yes-no)+' 份':'');
 get('empty').hidden=visible!==0;
}
for(const id of ['q','course','fmt'])get(id).addEventListener('input',update);
update();

