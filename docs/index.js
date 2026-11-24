'use strict';
const get = id => document.getElementById(id);
const rows = [...document.querySelectorAll('.entry')];
const groups = [...document.querySelectorAll('section.course')];
const filters = ['subject', 'course', 'type', 'fmt', 'tag'];
const params = new URLSearchParams(location.search);
const fold = text => text.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g, '');
let bodyIndex = null, pendingIndex = null, indexError = false;
for (const row of rows) row.dataset.baseHref = row.querySelector('.title').getAttribute('href');
for (const field of ['q', ...filters]) if (params.has(field)) get(field).value = params.get(field);
async function loadBodyIndex() {
  if (pendingIndex || bodyIndex || indexError) return;
  pendingIndex = fetch('search-index.json', {cache: 'no-cache'})
    .then(response => {
      if (!response.ok) throw new Error('Search index unavailable');
      return response.json();
    })
    .then(records => {
      const allowed = new Map(rows.map(row => [row.dataset.id, row.dataset.sha]));
      bodyIndex = new Map(records.filter(record => allowed.get(record.id) === record.sha256)
        .map(record => [record.id, {...record, folded: fold(record.pages.map(page => page.text).join(' '))}]));
    })
    .catch(() => { indexError = true; })
    .finally(() => { pendingIndex = null; refresh(false); });
}
function refresh(save) {
  const words = get('q').value.trim().split(/\s+/).filter(Boolean).map(fold);
  if (words.length && !bodyIndex && !indexError) loadBodyIndex();
  let count = 0;
  for (const row of rows) {
    const record = bodyIndex?.get(row.dataset.id);
    const corpus = fold(row.dataset.search + ' ' + row.dataset.tags) + (record?.folded || '');
    const visible = filters.every(field => !get(field).value ||
      (field === 'fmt' ? row.dataset.editions.split('|').includes(get(field).value) :
       field === 'tag' ? row.dataset.tags.split('|').includes(get(field).value) :
       row.dataset[field] === get(field).value)) && words.every(word => corpus.includes(word));
    row.hidden = !visible;
    const title = row.querySelector('.title');
    const excerpt = row.querySelector('.search-excerpt');
    title.setAttribute('href', row.dataset.baseHref);
    excerpt.hidden = true;
    excerpt.textContent = '';
    if (!visible) continue;
    count++;
    if (words.length && record) {
      const page = record.pages.find(page => words.every(word => fold(page.text).includes(word)))
        || record.pages.find(page => words.some(word => fold(page.text).includes(word)));
      if (page) {
        const plain = page.text.replace(/\s+/g, ' ').trim();
        const position = plain.toLocaleLowerCase().indexOf(get('q').value.trim().toLocaleLowerCase());
        const start = Math.max(0, position - 45);
        excerpt.textContent = (record.pdf_reader ? '第 ' + page.page + ' 页 · ' : '') +
          (start ? '…' : '') + plain.slice(start, start + 160) + (plain.length > start + 160 ? '…' : '');
        excerpt.hidden = false;
        if (record.pdf_reader) title.setAttribute('href', row.dataset.baseHref + '#page-' + page.page);
      }
    }
  }
  for (const group of groups) group.hidden = !group.querySelector('.entry:not([hidden])');
  const loading = words.length && !bodyIndex && !indexError;
  get('count').textContent = loading ? '正在检索正文…' :
    '当前显示 ' + count + ' 份' + (indexError && words.length ? '（正文搜索暂不可用，当前仅搜索题名和分类）' : '');
  get('empty').hidden = loading || count > 0;
  if (save) {
    const url = new URL(location.href);
    for (const field of ['q', ...filters]) {
      if (get(field).value) url.searchParams.set(field, get(field).value);
      else url.searchParams.delete(field);
    }
    history.replaceState(null, '', url);
  }
}
for (const field of ['q', ...filters]) get(field).addEventListener('input', () => refresh(true));
refresh(false);
