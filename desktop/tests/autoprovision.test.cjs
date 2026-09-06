'use strict';

const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {parseDotenv, loadDotenv, provisionFromDotenv, hasLaunchKeys} = require('../autoprovision.cjs');

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

test('loadDotenv matches Python first-wins and includes non-AUTO keys', () => {
  const dir = tmpdir();
  fs.mkdirSync(path.join(dir, 'secrets'));
  fs.writeFileSync(
    path.join(dir, 'secrets', 'glm_coding_plan.env'),
    'SUPEREZIO_GLM_CODING_PLAN_API_KEY=sk-glm-sidecar\n'
  );
  fs.writeFileSync(
    path.join(dir, '.env'),
    [
      'SUPEREZIO_DEEPSEEK_API_KEY=sk-env',
      'SUPEREZIO_GLM_CODING_PLAN_API_KEY=sk-glm-env',
      'SUPEREZIO_JWT_SECRET=jwt-from-env',
      'FINNHUB_API_KEY=fin-env',
    ].join('\n')
  );
  fs.writeFileSync(
    path.join(dir, '.env.local'),
    'SUPEREZIO_DEEPSEEK_API_KEY=sk-local\nFINNHUB_API_KEY=fin-local\n'
  );
  const loaded = loadDotenv([dir]);
  assert.equal(loaded.SUPEREZIO_DEEPSEEK_API_KEY, 'sk-local');
  assert.equal(loaded.SUPEREZIO_GLM_CODING_PLAN_API_KEY, 'sk-glm-sidecar');
  assert.equal(loaded.FINNHUB_API_KEY, 'fin-local');
  assert.equal(loaded.SUPEREZIO_JWT_SECRET, 'jwt-from-env');
});

test('later dotenv dir overlays earlier dir without dropping extra keys', () => {
  const repo = tmpdir();
  const profile = tmpdir();
  fs.writeFileSync(
    path.join(repo, '.env'),
    'SUPEREZIO_DEEPSEEK_API_KEY=sk-repo\nSUPEREZIO_JWT_SECRET=jwt-repo\n'
  );
  fs.writeFileSync(path.join(profile, '.env'), 'SUPEREZIO_DEEPSEEK_API_KEY=sk-profile\n');
  const loaded = loadDotenv([repo, profile]);
  assert.equal(loaded.SUPEREZIO_DEEPSEEK_API_KEY, 'sk-profile');
  assert.equal(loaded.SUPEREZIO_JWT_SECRET, 'jwt-repo');
});

test('hasLaunchKeys accepts DeepSeek or GLM without logging values', () => {
  assert.equal(hasLaunchKeys({}), false);
  assert.equal(hasLaunchKeys({SUPEREZIO_DEEPSEEK_API_KEY: '  '}), false);
  assert.equal(hasLaunchKeys({SUPEREZIO_DEEPSEEK_API_KEY: 'sk-ds'}), true);
  assert.equal(hasLaunchKeys({SUPEREZIO_GLM_CODING_PLAN_API_KEY: 'sk-glm'}), true);
});
