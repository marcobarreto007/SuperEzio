# F51 Risk Report — SuperEzio v3.0.1

**Data**: 2026-05-13

## Riscos resolvidos

### R1 — Input/output guard no pipeline

`SecurityContext` segue wired no runtime e output do CEO passa por sanitizacao.

### R2 — Gateway incompleto

Rotas sensiveis passam por auth/rate limit. `/health` e assets estaticos sao os unicos caminhos publicos intencionais.

### R3 — Health expondo detalhe

`/health` agora retorna apenas liveness minimal. Diagnostico completo foi movido para `/health/details`, protegido pelo gateway.

### R4 — Fallback falso do PennyLab

Falha do PennyLab nao gera mais `WATCH_ONLY`; erro fica estruturado e nao entra no prompt como veredito.

### R5 — Modelos CrisisMath com nomes mais fortes que a implementacao

Sensores mantem nomes historicos por compatibilidade, mas expõem `details["implementation"]` e notas de implementacao.

### R6 — Falhas silenciosas de alto impacto

Runtime, DataHub, F51 adapter, memoria, notificacoes e reward journal agora registram falhas antes silenciosas.

## Riscos remanescentes

### R7 — Chaves antigas no historico

Relatorio interno: `docs/internal/SECURITY_LEAKED_KEYS.md`.

Impacto: qualquer chave ainda ativa que apareceu no historico deve ser considerada comprometida.

Mitigacao: revogar/rotacionar DeepSeek, TwelveData, Alpha Vantage e NewsAPI antes de entrega publica.

### R8 — Type check nao executado

`pyright` nao esta instalado neste ambiente.

Mitigacao: instalar pyright ou adicionar ao toolchain antes de exigir type gate bloqueante.

### R9 — Smoke live depende de ambiente

CEO local, provedores de mercado e APIs externas dependem de modelo/credenciais/servicos nao versionados.

Mitigacao: rodar smoke com `.env` real apos rotacao de chaves.

## Veredito de risco

Risco tecnico do codigo: baixo para demo/local.

Risco operacional para entrega externa: medio ate a rotacao das chaves historicas.
