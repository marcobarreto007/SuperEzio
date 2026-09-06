'use strict';

const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {parseDotenv, provisionFromDotenv} = require('../autoprovision.cjs');

function tmpdir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'superezio-ap-'));
}

test('parseDotenv reads KEY=VALUE with comments, quotes and export', () => {
  const dir = tmpdir();
  const file = path.join(dir, 'dotenv');
  fs.writeFileSync(file, [
    '# comentario',
    'SUPEREZIO_DEEPSEEK_API_KEY=sk-test',
    'FINNHUB_API_KEY="quoted-value"',
    'export TWELVE_DATA_API_KEY=twelve',
    'ALPHA_VANTAGE_API_KEY=\'single\'',
    'INVALID_LINE_WITHOUT_EQUALS',
    '',
  ].join('\n'));
  const parsed = parseDotenv(file);
  assert.equal(parsed.SUPEREZIO_DEEPSEEK_API_KEY, 'sk-test');
  assert.equal(parsed.FINNHUB_API_KEY, 'quoted-value');
  assert.equal(parsed.TWELVE_DATA_API_KEY, 'twelve');
  assert.equal(parsed.ALPHA_VANTAGE_API_KEY, 'single');
});

test('parseDotenv tolerates missing file', () => {
  assert.deepEqual(parseDotenv(path.join(tmpdir(), 'nope')), {});
});

test('provisionFromDotenv collects keys and lets .env.local win', () => {
  const dir = tmpdir();
  fs.writeFileSync(
    path.join(dir, '.env'),
    'SUPEREZIO_DEEPSEEK_API_KEY=sk-main\nFINNHUB_API_KEY=from-main\n'
  );
  fs.writeFileSync(
    path.join(dir, '.env.local'),
    'SUPEREZIO_DEEPSEEK_API_KEY=sk-local\n'
  );
  const settings = provisionFromDotenv([dir]);
  assert.equal(settings.SUPEREZIO_DEEPSEEK_API_KEY, 'sk-local');
  assert.equal(settings.FINNHUB_API_KEY, 'from-main');
});

test('provisionFromDotenv returns null when nothing is found', () => {
  assert.equal(provisionFromDotenv([tmpdir()]), null);
});
