'use strict';
const get = id => document.getElementById(id);
const rows = [...document.querySelectorAll('.entry')];
const groups = [...document.querySelectorAll('section.course')];
const filters = ['subject','course','type','fmt'];
const params = new URLSearchParams(location.search);
for (const f of ['q',...filters]) if (params.has(f)) get(f).value = params.get(f);
function refresh(save) {
  const words = get('q').value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  let count = 0;
  for (const row of rows) {
    const visible = filters.every(f => !get(f).value || (f === 'fmt'
      ? row.dataset.editions.split('|').includes(get(f).value) : row.dataset[f] === get(f).value))
      && words.every(word => row.dataset.search.includes(word));
    row.hidden = !visible;
    if (visible) count++;
  }
  for (const course of groups) course.hidden = !course.querySelector('.entry:not([hidden])');
  get('count').textContent = '当前显示 ' + count + ' 份';
  get('empty').hidden = count > 0;
  if (save) {
    const url = new URL(location.href);
    for (const f of ['q',...filters]) {
      if (get(f).value) url.searchParams.set(f,get(f).value); else url.searchParams.delete(f);
    }
    history.replaceState(null,'',url);
  }
}
for (const f of [...filters,'q']) get(f).addEventListener('input',() => refresh(true));
refresh(false);
