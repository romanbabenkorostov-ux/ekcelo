import { test } from 'node:test';
import assert from 'node:assert/strict';
import { escapeHtml, escapeXml } from '../../viewer/core/escape.js';

test('escapeHtml: replaces all 5 special chars', () => {
  assert.equal(escapeHtml(`<b>"Hi" & 'yo'</b>`),
    '&lt;b&gt;&quot;Hi&quot; &amp; &#39;yo&#39;&lt;/b&gt;');
});

test('escapeHtml: idempotent on safe string', () => {
  assert.equal(escapeHtml('plain text 123'), 'plain text 123');
});

test('escapeHtml: coerces non-string via String()', () => {
  assert.equal(escapeHtml(42), '42');
  assert.equal(escapeHtml(null), 'null');
  assert.equal(escapeHtml(undefined), 'undefined');
});

test('escapeXml: replaces all 5 special chars (single-quote → &apos;)', () => {
  assert.equal(escapeXml(`<a attr="x">'&y'</a>`),
    '&lt;a attr=&quot;x&quot;&gt;&apos;&amp;y&apos;&lt;/a&gt;');
});

test('escapeXml: null/undefined → empty string (preserves index.html behaviour)', () => {
  assert.equal(escapeXml(null), '');
  assert.equal(escapeXml(undefined), '');
});

test('escapeXml: idempotent on safe string', () => {
  assert.equal(escapeXml('safe-name_42'), 'safe-name_42');
});
