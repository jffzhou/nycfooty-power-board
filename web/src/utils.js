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