// viewer/ui/bridge.js — временный мост от модулей viewer/core/ к window-глобалам,
// которые ещё используются классическими <script> в viewer/index.html.
// ADR-003: убирается, когда последний классический вызывающий переедет в модули.

import { sha256Hex } from '../core/hashing.js';
import { escapeHtml, escapeXml } from '../core/escape.js';

window.__ekceloSha256Hex = sha256Hex;
window._escapeHtml = escapeHtml;
window._escapeXml = escapeXml;
