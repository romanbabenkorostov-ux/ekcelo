// viewer/core/hashing.js — pure SHA-256 hex. ADR-003 / viewer/core.
// Web Crypto API доступно в браузере и в Node 20+ через globalThis.crypto.

export async function sha256Hex(s) {
  const bytes = new TextEncoder().encode(String(s));
  const buf = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(buf))
    .map(x => x.toString(16).padStart(2, '0'))
    .join('');
}
