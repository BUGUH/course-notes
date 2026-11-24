'use strict';
(() => {
  const root = document.documentElement;
  root.classList.add('has-script');
  try {
    const pref = localStorage.getItem('course-notes-theme');
    if (pref === 'light' || pref === 'dark') root.dataset.theme = pref;
  } catch {}
  document.addEventListener('DOMContentLoaded', () => {
    const menu = document.getElementById('menu-toggle');
    const navigation = document.getElementById('site-navigation');
    if (menu && navigation) {
      function openMenu(open) {
        navigation.classList.toggle('is-open', open);
        menu.setAttribute('aria-expanded', String(open));
        menu.setAttribute('aria-label', open ? '收起站点导航' : '展开站点导航');
      }
      menu.addEventListener('click', () => openMenu(menu.getAttribute('aria-expanded') !== 'true'));
      document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') {
          openMenu(false);menu.focus();
        }
      });
    }
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
