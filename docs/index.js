'use strict';

const byId = id => document.getElementById(id);
const rows = Array.from(document.querySelectorAll('.entry'));
const courses = Array.from(document.querySelectorAll('.course'));
const filters = ['course', 'type', 'fmt'];

function applyFilters() {
  const words = byId('q').value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  let count = 0;
  for (const row of rows) {
    const visible = filters.every(name => {
      const selected = byId(name).value;
      if (!selected) return true;
      return name === 'fmt'
        ? (row.dataset.editions || row.dataset.fmt).split('|').includes(selected)
        : row.dataset[name] === selected;
    })
      && words.every(word => row.dataset.search.includes(word));
    row.hidden = !visible;
    if (visible) count++;
  }
  for (const course of courses) course.hidden = !course.querySelector('.entry:not([hidden])');
  byId('count').textContent = '当前显示 ' + count + ' 份';
  byId('empty').hidden = count > 0;
}

for (const name of ['q', ...filters]) byId(name).addEventListener('input', applyFilters);
applyFilters();

