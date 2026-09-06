// Auto-provision: usa as chaves que o operador ja tem no dotenv do projeto.
// Produto de uso pessoal/familiar: nenhuma tela de chave manual quando o
// .env (ou .env.local) da maquina ja tem as chaves. Modulo puro (sem electron)
// para poder ser testado com `node --test`.
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const AUTO_KEYS = [
  'SUPEREZIO_DEEPSEEK_API_KEY',
  'SUPEREZIO_GLM_CODING_PLAN_API_KEY',
  'FINNHUB_API_KEY',
  'TWELVE_DATA_API_KEY',
  'ALPHA_VANTAGE_API_KEY',
];

// Mesma ordem do runtime Python (core.config.secrets._env_files): first-wins.
const DOTENV_RELATIVE = [
  path.join('secrets', 'glm_coding_plan.env'),
  '.env.local',
  '.env',
];

function hasLaunchKeys(env) {
  if (!env || typeof env !== 'object') return false;
  const deepseek = String(env.SUPEREZIO_DEEPSEEK_API_KEY || '').trim();
  const glm = String(env.SUPEREZIO_GLM_CODING_PLAN_API_KEY || '').trim();
  return Boolean(deepseek || glm);
}

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

function loadDotenvFromDir(dir) {
  const local = {};
  for (const rel of DOTENV_RELATIVE) {
    const parsed = parseDotenv(path.join(dir, rel));
    for (const [name, value] of Object.entries(parsed)) {
      const trimmed = String(value || '').trim();
      if (!(name in local) && trimmed) local[name] = trimmed;
    }
  }
  return local;
}

function loadDotenv(dirs) {
  const merged = {};
  for (const dir of dirs) Object.assign(merged, loadDotenvFromDir(dir));
  return merged;
}

function provisionFromDotenv(dirs) {
  const merged = loadDotenv(dirs);
  const settings = {};
  for (const name of AUTO_KEYS) {
    if (merged[name]) settings[name] = merged[name];
  }
  return Object.keys(settings).length ? settings : null;
}

module.exports = {
  parseDotenv,
  loadDotenv,
  provisionFromDotenv,
  hasLaunchKeys,
  AUTO_KEYS,
  DOTENV_RELATIVE,
};
