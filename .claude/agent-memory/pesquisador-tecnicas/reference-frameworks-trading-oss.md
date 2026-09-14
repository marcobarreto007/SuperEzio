---
name: reference-frameworks-trading-oss
description: Mapa de licenças e atividade (verificado 2026-09-14 via API do GitHub) dos frameworks de trading open source candidatos a clonar — quais servem equities e quais são armadilha de licença
metadata:
  type: reference
---

Verificado em 2026-09-14 via `api.github.com/repos/...` (fonte primária: license.spdx_id + pushed_at).

**Armadilhas de licença já confirmadas — não repetir a pesquisa:**
- `vectorbt` (polakowo/vectorbt): **Apache-2.0 + Commons Clause**, não é OSI-approved. `LICENSE.md` traz o texto da Commons Clause v1.0 ("right to Sell the Software" excluído). Uso interno de trading é ok, mas não é licença permissiva limpa.
- `mlfinlab` (hudson-and-thames): **licença proprietária comercial** ("Copyright Protection Notice and Licensing Agreement", "ArbitrageLab Business License Agreement"), push 2023-10-02. **Não é open source** — a implementação canônica de barreira tripla do López de Prado está atrás disso.
- `StockSharp/StockSharp`: **licença custom proprietária** ("StockSharp Custom License Notice", "not licensed under a general-purpose open source license"), apesar de spdx_id NOASSERTION no GitHub.
- `kernc/backtesting.py`: **AGPL-3.0** (ativo, 2026-08-05).
- `backtrader`: GPL-3.0 e **parado** (2024-08-19).
- GPL-3.0 (freqtrade, OctoBot) e LGPL-3.0 (nautilus_trader) são ok para uso interno, mas obrigam se houver distribuição.

**Licenças limpas e vivas:**
- `QuantConnect/Lean` — Apache-2.0, C#, push 2026-09-12. **Só a doc de asset classes tem US Equity e India Equity; não há "Canada Equity"/TSX.**
- `zipline-reloaded` — Apache-2.0, push 2026-01-06, `requires-python >=3.10`, equities-first, 26 deps (sqlalchemy/tables/h5py/bcolz-zipline).
- `stefan-jansen/machine-learning-for-trading` — MIT, push 2026-09-14, 27 capítulos, 3ª ed.
- `ml4t/engineer` — MIT, push 2026-09-10, pub `ml4t-engineer` 0.1.4 no PyPI (2026-09-09), **requires-python >=3.12,<3.15**.
- `skfolio` — BSD-3, push 2026-09-13. `PyPortfolioOpt` — MIT, 2026-07-07. `Riskfolio-Lib` — BSD-3, 2026-08-18.
- `quantstats` — Apache-2.0, 2026-07-20. `APScheduler` — MIT, 2026-09-10. `ib_async` — BSD-2, 2026-08-19.
- `gerrymanoim/exchange_calendars` — Apache-2.0, 2026-09-02; tem `exchange_calendar_xtse.py` (**feriados da TSX**).
- `qstrader` — MIT, mas parado em 2024-06-30. `blankly` — LGPL-3.0, parado 2024-12-30. `timeseriescv` — MIT, parado 2022.

**Cripto-only (não serve equities):** freqtrade, hummingbot, OctoBot, jesse.

**Caminhos úteis confirmados (existem no repo hoje):**
- `QuantConnect/Lean` → `Algorithm.Framework/Risk/` (`.cs` + `.py`): TrailingStopRiskManagementModel, MaximumDrawdownPercentPerSecurity, MaximumDrawdownPercentPortfolio, MaximumUnrealizedProfitPercentPerSecurity, MaximumSectorExposureRiskManagementModel.
- `ml4t/engineer` → `src/ml4t/engineer/labeling/`: triple_barrier.py, atr_barriers.py, meta_labels.py, uniqueness.py (~500 linhas, polars + numba).
- `skfolio` → `src/skfolio/optimization/cluster/hierarchical/_hrp.py`; `src/skfolio/model_selection/_combinatorial.py` tem `class CombinatorialPurgedCV`.

Relacionado: [[project-superezio-buracos-e-fontes]]
