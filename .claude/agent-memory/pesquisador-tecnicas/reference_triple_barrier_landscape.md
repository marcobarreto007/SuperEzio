---
name: reference-triple-barrier-landscape
description: Onde está (e onde não está) implementação livre de triple barrier, meta-labeling e purged K-fold em 2026-09 — mlfinlab morreu, os substitutos são mlfinpy e purgedcv
metadata:
  type: reference
---

Mapa externo levantado em 2026-09-14 para o labeler de barreira tripla / meta-labeling do SuperEzio (regra 7 do CLAUDE.md exige P(Y=1) < 0.55 → ABSTAIN).

**mlfinlab (Hudson & Thames): morto como fonte livre.**
- Removido do PyPI: `https://pypi.org/project/mlfinlab/` responde 404 e libraries.io registra "This package has been removed from Pypi … cannot be used anymore". Sem pacote conda-forge (404).
- O repo `hudson-and-thames/mlfinlab` (4.9k★, último push 2023-10-02) é só bug tracker, licença "all rights reserved" (NOASSERTION no GitHub). Os forks que preservam o código antigo (ex. `mnewls/MLFINLAB`, 26★) têm licença null/NOASSERTION → não reusáveis. Não há caminho legal/gratuito pelo mlfinlab.

**Substitutos usados na prática:**
- `baobach/mlfinpy` — MIT, Python >=3.11, PyPI 0.1.2 (2024-10-09), último push 2025-01-23. Tem `labeling/labeling.py` (`triple_barriers`, `add_vertical_barrier`, `get_events`, `barrier_touched`, `get_bins`) e `cross_validation/cross_validation.py` (`PurgedKFold` com `pct_embargo`, `ml_cross_val_score`). Tem testes (`tests/test_labels.py`, `tests/test_cross_validation.py`).
- `eslazarev/purged-cross-validation` (PyPI `purgedcv`) — MIT, 0.1.6 de 2026-09-04, ativo, deps compatíveis com env numpy 2.x/pandas 3.x. Entrega `PurgedKFold`, `CombinatorialPurgedCV`, `apply_embargo` (3 modos), `audit_splitter`, DSR/PBO.
- `triple-barrier` no PyPI é do `mchiuminatto/triple_barrier` (MIT, pina `matplotlib==3.8.2`), NÃO do `becryptoconfident/triple-barrier` que diz no README ser instalável por esse nome.

**Armadilha de dependência (crítica nesta máquina):** `mlfinpy` publicado pina `numpy<1.27` e `pandas<3.0.0` + `numba<0.61`; a env travada do SuperEzio está em numpy 2.2.6 / pandas 3.0.2 / sklearn 1.8.0 / torch 2.13.0. `pip install mlfinpy` forçaria downgrade e quebraria a env.
**How to apply:** copiar os 2 arquivos MIT (`mlfinpy/labeling/labeling.py` + `mlfinpy/util/multiprocess.py`, que só importam numpy/pandas/stdlib) em vez de instalar o pacote; usar `num_threads=1` (caminho sequencial, sem `mp.Pool`, seguro no Windows).

**Bug confirmado por leitura do código:** o `CombinatorialPurgedKFold` do mlfinpy zera o próprio embargo (`self.embargo = 0` antes de `embargo = delta * self.embargo`) → CPCV sem embargo. Para CPCV, usar `purgedcv`.

Não confirmado: se o bug do CPCV veio do mlfinlab original, e a divisão histórico gratuito/pago do mlfinlab (página do PyPI removida, archive.org inacessível nesta sessão).
