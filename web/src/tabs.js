export function initTabs(onShow) {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const stickyStart = document.querySelector('.metrics');

  function show(name, { focus = false } = {}) {
    const target = tabs.find((tab) => tab.dataset.tab === name) ?? tabs[0];
    for (const tab of tabs) {
      const active = tab === target;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      document.getElementById(tab.getAttribute('aria-controls')).hidden = !active;
    }
    if (focus) target.focus();
    if (location.hash !== `#${target.dataset.tab}`) history.replaceState(null, '', `#${target.dataset.tab}`);
    const top = stickyStart.offsetTop + stickyStart.offsetHeight;
    if (window.scrollY > top) window.scrollTo({ top });
    onShow?.(target.dataset.tab);
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => show(tab.dataset.tab));
    tab.addEventListener('keydown', (event) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!step) return;
      event.preventDefault();
      show(tabs[(index + step + tabs.length) % tabs.length].dataset.tab, { focus: true });
    });
  });
  window.addEventListener('hashchange', () => show(location.hash.slice(1)));
  show(location.hash.slice(1));
  return show;
}
