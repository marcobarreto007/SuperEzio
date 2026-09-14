---
name: project-superezio-buracos-e-fontes
description: SuperEzio (paper trading TSX/TD, Python 3.11, DeepSeek) — os três buracos (fechador, labeler, agendador) e de onde clonar cada um, com os custos reais de adaptação
metadata:
  type: project
---

Estado em 2026-09-14. O SuperEzio é pipeline próprio (experts → judge → auditor → orquestrador), não um bot de exchange; qualquer framework entra como **doador de peça**, não como runtime.

**Buracos e doador escolhido:**
- Fechador de posição → `QuantConnect/Lean`, `Algorithm.Framework/Risk/*.py` (Apache-2.0, Python). Contrato: `manage_risk(algorithm, targets)` devolve `List[PortfolioTarget]`; liquidação = `PortfolioTarget(symbol, 0)` + `algorithm.Insights.Cancel(...)`. Trailing default 5%. **Não é plug-and-play**: as classes herdam de `RiskManagementModel` e usam `algorithm.Securities`; adaptar = reescrever ~100 linhas contra a API interna.
- Labeler de barreira tripla → `ml4t/engineer` (MIT). Bloqueio: **exige Python >=3.12 e usa polars + numba**; o SuperEzio é 3.11. Como é MIT, portar a lógica de barreira para pandas é legítimo, mas é hipótese de engenharia, não medição.
- Agendador → APScheduler (MIT) + `exchange_calendars` XTSE para não operar em feriado canadense.
- Backtest honesto → zipline-reloaded (Apache-2.0, ≥3.10, equities). Custo: 26 deps novas + bundle de dados.
- Journal → quantstats (Apache-2.0).

**Restrição de mercado que nenhum framework cobre:** não localizei API pública do TD Direct Investing (não verifiquei na fonte oficial da TD). Nenhum framework OSS conecta lá. O Lean na nuvem não tem "Canada Equity" na doc de asset classes. `nautilus_trader` só chega em equities via adapter IBKR (que está offline no projeto).

**Why:** o usuário pediu explicitamente "antes de escrever, pesquise se alguém fez melhor; se fez, clone e adapte", com trava dura de custo zero e preferência por licença permissiva.
**How to apply:** ao propor peça nova, dizer de qual repo ela veio, com licença, e quanto custa adaptar; checar antes se o Python 3.11 do projeto bate com o `requires-python` do pacote. Antes de clonar/adaptar qualquer coisa: `git init` — o SuperEzio **não é repositório git**, logo não há como reverter hoje.

Relacionado: [[reference-frameworks-trading-oss]]
