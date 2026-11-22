'use strict';
(() => {
  const root = document.documentElement;
  try {
    const pref = localStorage.getItem('course-notes-theme');
    if (pref === 'light' || pref === 'dark') root.dataset.theme = pref;
  } catch {}
  document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('theme');
    if (!button) return;
    function isDark() { return (root.dataset.theme || (matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light')) === 'dark'; }
    function label() { button.textContent = isDark() ? '☀' : '◐'; button.setAttribute('aria-label', isDark() ? '切换为浅色' : '切换为深色'); }
    label(); button.addEventListener('click', () => {
      root.dataset.theme = isDark() ? 'light' : 'dark';
      try {localStorage.setItem('course-notes-theme',root.dataset.theme);} catch {}
      label();
    });
  });
})();
