// Ekcelo token-system v1 — stateless self-contained URL shortener.
// Алгоритм:
//   encode: url -> base64url(UTF-8(url)) без padding
//   decode: токен -> URL (после восстановления padding и проверки схемы)
// Никакого реестра, состояния, шифрования.

export const ALLOWED_SCHEMES = ["http:", "https:"];
export const DEFAULT_BASE = "https://ekcelo.ru/";

function b64urlEncode(bytes) {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlDecode(token) {
  const norm = token.replace(/-/g, "+").replace(/_/g, "/");
  const pad = norm.length % 4 === 0 ? "" : "=".repeat(4 - (norm.length % 4));
  const bin = atob(norm + pad);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

function isAllowedUrl(s) {
  try {
    const u = new URL(s);
    return ALLOWED_SCHEMES.includes(u.protocol);
  } catch {
    return false;
  }
}

export function encode(url) {
  if (typeof url !== "string" || !isAllowedUrl(url)) {
    throw new Error("encode: требуется http(s) URL");
  }
  return b64urlEncode(new TextEncoder().encode(url));
}

export function decode(token) {
  if (typeof token !== "string" || token.length === 0) return null;
  if (!/^[A-Za-z0-9_-]+$/.test(token)) return null;
  try {
    const bytes = b64urlDecode(token);
    const url = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    return isAllowedUrl(url) ? url : null;
  } catch {
    return null;
  }
}

export function buildShortUrl(url, base = DEFAULT_BASE) {
  return base + "?t=" + encode(url);
}

export function parseShortUrl(href) {
  try {
    const u = new URL(href);
    const t = u.searchParams.get("t");
    return t ? decode(t) : null;
  } catch {
    return null;
  }
}
