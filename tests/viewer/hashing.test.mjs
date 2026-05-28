import { test } from 'node:test';
import assert from 'node:assert/strict';
import { sha256Hex } from '../../viewer/core/hashing.js';

test('sha256Hex of empty string — known vector', async () => {
  assert.equal(
    await sha256Hex(''),
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
  );
});

test('sha256Hex of "abc" — known vector', async () => {
  assert.equal(
    await sha256Hex('abc'),
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
  );
});

test('sha256Hex of non-ASCII (UTF-8) — known vector', async () => {
  // SHA-256 of UTF-8 bytes of "тест" (D1 82 D0 B5 D1 81 D1 82).
  // Cross-check: `printf '%s' тест | sha256sum`.
  assert.equal(
    await sha256Hex('тест'),
    'e34f6dec12c4f4599eba078f31ae8139420d21b1bd2d7ced7d22b09c2074fb48'
  );
});

test('sha256Hex returns 64 hex chars', async () => {
  const h = await sha256Hex('anything');
  assert.match(h, /^[0-9a-f]{64}$/);
});
