---
name: licencas-bibliotecas-trading
description: Mapa de licença/viabilidade das bibliotecas de trading avaliadas para o SuperEzio (quais são armadilha GPL/AGPL/paga) — verificado 2026-09-14
metadata:
  type: reference
---

Levantamento feito em **2026-09-14** via GitHub API e PyPI JSON (WebSearch estava esgotado: 200/200).
Serve para não refazer a pesquisa. Números de atividade envelhecem — reconferir antes de decidir.

**Armadilhas para projeto fechado (não usar):**
- `kernc/backtesting.py` → **AGPL-3.0** (não MIT, como muita gente repete de memória).
- `mementum/backtrader` → **GPL-3.0**, parado em 2024-08-19.
- `freqtrade/freqtrade` → **GPL-3.0**. O bom código de borda dele (gap de stop) **não pode ser copiado**; a *regra* de mercado pode ser reimplementada.
- `Lumiwealth/lumibot` → **GPL-3.0**.
- `polakowo/vectorbt` e `edtechre/pybroker` → **Apache-2.0 + Commons Clause** (proíbe "Sell the Software"). GitHub reporta `NOASSERTION` nos dois.
- `hudson-and-thames/mlfinlab` → hoje é o **"ArbitrageLab Business License Agreement"**: pago, fee de assinatura, webhooks rastreando chamadas. **Fora do PyPI (404)**. Bloqueado pela regra de não gastar dinheiro.

**Utilizáveis:**
- `baobach/mlfinpy` → **MIT**, reimplementação clean-room (diz explicitamente que o MlFinLab é closed-source). Python `>=3.11,<4.0`. **Mas**: alpha (`Development Status :: 3`), 2 releases no PyPI, último commit 2025-01-23. Deps pinam `numpy<1.27` → **conflita com o `numpy>=1.24,<2.6` do SuperEzio**; instalar sem `--no-deps` força downgrade. Copiar a função é mais barato que instalar.
- `jesse-ai/jesse` → **MIT puro** (confirmado no LICENSE raw), ativo. Mas é framework completo, self-hosted.
- `nautechsystems/nautilus_trader` → **LGPL-3.0**, muito ativo.
- `stefan-jansen/zipline-reloaded` → Apache-2.0.
- `QuantConnect/Lean` → Apache-2.0, mas C#.
- `agronholm/apscheduler` → **MIT**, ativo. Candidato a agendador.

**Não encontrado:** biblioteca pequena e mantida cujo único trabalho seja rastrear stop/alvo/expiração. As buscas por `trailing stop`, `stoploss in:name`, `exit manager` devolvem bots inteiros (crypto), não bibliotecas; as raras MIT são repositórios pessoais de 0-5 estrelas.

Relacionado: [[superezio-fechador-posicao-gap]].
