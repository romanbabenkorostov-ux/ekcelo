// viewer/core/escape.js — pure HTML/XML escape helpers. ADR-003 / viewer/core.
// Тело перенесено 1:1 из viewer/index.html (_escapeHtml, _escapeXml).

const HTML_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const XML_MAP  = { '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&apos;', '"': '&quot;' };

export function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => HTML_MAP[c]);
}

// XML escape для атрибутов / текста элементов. НЕ для CDATA — оставляй CDATA как есть.
export function escapeXml(s) {
  return String(s || '').replace(/[&<>'"]/g, c => XML_MAP[c]);
}
