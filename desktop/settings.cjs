const allowed = new Set(['SUPEREZIO_DEEPSEEK_API_KEY', 'FINNHUB_API_KEY', 'TWELVE_DATA_API_KEY', 'ALPHA_VANTAGE_API_KEY']);
function validateSettings(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Configuração inválida.');
  const result = {};
  for (const [name, value] of Object.entries(input)) {
    if (!allowed.has(name) || typeof value !== 'string' || value.length > 4096 || /[\r\n\0]/.test(value)) throw new Error('Configuração inválida.');
    if (value.trim()) result[name] = value.trim();
  }
  if (!result.SUPEREZIO_DEEPSEEK_API_KEY) throw new Error('Informe a chave da API DeepSeek.');
  return result;
}
module.exports = {validateSettings};
