export function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

export function percentage(value, digits = 0) {
  return `${(value * 100).toFixed(digits)}%`;
}

export function signed(value, digits = 0) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`;
}

// Keep in sync with the 640px media query in styles.css.
export const PHONE = window.matchMedia('(max-width: 640px)');

export function centerInScroller(scroller, element) {
  scroller.scrollTo({ left: element.offsetLeft - (scroller.clientWidth - element.offsetWidth) / 2, behavior: 'smooth' });
}