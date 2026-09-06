// Auto-provision: usa as chaves que o operador ja tem no dotenv do projeto.
// Produto de uso pessoal/familiar: nenhuma tela de chave manual quando o
// .env (ou .env.local) da maquina ja tem as chaves. Modulo puro (sem electron)
// para poder ser testado com `node --test`.
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const AUTO_KEYS = [
  'SUPEREZIO_DEEPSEEK_API_KEY',
  'FINNHUB_API_KEY',
  'TWELVE_DATA_API_KEY',
  'ALPHA_VANTAGE_API_KEY',
];

function parseDotenv(file) {
  const result = {};
  if (!fs.existsSync(file)) return result;
  const text = fs.readFileSync(file, 'utf8');
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const m = line.match(/^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (!m) continue;
    let value = m[2].trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    result[m[1]] = value;
  }
  return result;
}

function provisionFromDotenv(dirs) {
  const merged = {};
  for (const dir of dirs) {
    Object.assign(merged, parseDotenv(path.join(dir, '.env')));
    Object.assign(merged, parseDotenv(path.join(dir, '.env.local'))); // .env.local vence
  }
  const settings = {};
  for (const name of AUTO_KEYS) {
    if (merged[name] && merged[name].trim()) settings[name] = merged[name].trim();
  }
  return Object.keys(settings).length ? settings : null;
}

module.exports = {parseDotenv, provisionFromDotenv, AUTO_KEYS};
