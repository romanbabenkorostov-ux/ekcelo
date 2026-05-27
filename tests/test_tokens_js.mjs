// Node-харнес: сверяет JS-реализацию viewer/tokens.js с фикстурой
// tests/fixtures/token_roundtrip.json (генерируется Python-тестом).
//
// Запуск: node tests/test_tokens_js.mjs

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

const { encode, decode } = await import(path.join(ROOT, "viewer", "tokens.js"));

const fxPath = path.join(ROOT, "tests", "fixtures", "token_roundtrip.json");
if (!fs.existsSync(fxPath)) {
  console.error("Нет фикстуры. Запусти сначала pytest tests/test_ekcelo_tokens.py.");
  process.exit(2);
}
const cases = JSON.parse(fs.readFileSync(fxPath, "utf-8"));

let failed = 0;
for (const { url, token } of cases) {
  const enc = encode(url);
  const dec = decode(token);
  if (enc !== token) {
    failed++;
    console.error(`encode mismatch for ${url}\n  expected: ${token}\n  got:      ${enc}`);
  }
  if (dec !== url) {
    failed++;
    console.error(`decode mismatch for ${token}\n  expected: ${url}\n  got:      ${dec}`);
  }
}

// Bad inputs.
const bad = ["", "!!!", "has space", "ZnRwOi8vYS5jb20"];
for (const t of bad) {
  if (decode(t) !== null) {
    failed++;
    console.error(`decode should reject ${JSON.stringify(t)}`);
  }
}

if (failed) {
  console.error(`FAILED (${failed})`);
  process.exit(1);
}
console.log(`OK (${cases.length} round-trips + ${bad.length} rejects)`);
