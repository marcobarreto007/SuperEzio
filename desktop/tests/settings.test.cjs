const {test} = require('node:test');
const assert = require('node:assert/strict');
const {validateSettings} = require('../settings.cjs');
test('requires customer key and trims inputs', () => {
  assert.deepEqual(validateSettings({SUPEREZIO_DEEPSEEK_API_KEY:' test ',FINNHUB_API_KEY:''}),{SUPEREZIO_DEEPSEEK_API_KEY:'test'});
  assert.throws(() => validateSettings({}));
});
test('rejects environment injection and unexpected fields', () => {
  assert.throws(() => validateSettings({SUPEREZIO_DEEPSEEK_API_KEY:'a\nb'}));
  assert.throws(() => validateSettings({SUPEREZIO_DEEPSEEK_API_KEY:'test',NODE_OPTIONS:'--inspect'}));
});
