# SuperEzio Frontpage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved SuperEzio Trust OS frontpage and serve it from the FastAPI app without restoring the removed `ui-chat` terminal.

**Architecture:** Add a new static `frontend/` surface with `index.html`, `styles.css`, and `app.js`; mount it from `agent_server.main` at `/frontend`; serve `frontend/index.html` from `/` when present while preserving an API JSON fallback if the files are missing. The first implementation is a safe visual shell: it consumes `/health` and `/product/manifest`, but does not yet make live financial recommendations.

**Tech Stack:** FastAPI static file serving, vanilla HTML/CSS/JS, local pytest/TestClient checks, optional Playwright screenshot verification if available.

---

## File Structure

- Create `frontend/index.html`: semantic first screen, five-destination navigation, hero, product preview, Decision Room preview, trust stack, and fallback messaging.
- Create `frontend/styles.css`: responsive Trust OS visual system, light landing surface, dark Decision Room panel, stable dimensions, accessibility states.
- Create `frontend/app.js`: health/manifest fetches, status rendering, nav/CTA interactions, safe sample Decision Brief rendering, graceful offline states.
- Modify `src/agent_server/main.py`: mount `/frontend` static assets and serve `frontend/index.html` at `/` when it exists.
- Modify `tests/test_agent_server_smoke.py`: update root expectations from `ui_removed` JSON to the new HTML frontpage and static asset route.
- Modify `tests/test_production_gate.py`: keep legacy `ui-chat/` and `assets/` removed, add checks that `frontend/` has the required first-screen files.

Do not modify `.env.example`, `.pre-commit-config.yaml`, or unrelated backend files if they are already dirty in the working tree.

---

### Task 1: Add Server And Asset Tests

**Files:**
- Modify: `tests/test_agent_server_smoke.py`
- Modify: `tests/test_production_gate.py`

- [ ] **Step 1: Update the smoke test for the new root frontpage**

In `tests/test_agent_server_smoke.py`, replace this block inside `test_agent_server_serves_core_endpoints`:

```python
        root = client.get("/")
        assert root.status_code == 200
        assert root.json()["status"] == "ui_removed"
```

with:

```python
        root = client.get("/")
        assert root.status_code == 200
        assert "text/html" in root.headers.get("content-type", "")
        assert "SuperEzio Trust OS" in root.text
        assert "Decisao financeira com alivio auditavel" in root.text

        frontend_js = client.get("/frontend/app.js")
        assert frontend_js.status_code == 200
        assert "initializeSuperEzioFrontpage" in frontend_js.text
```

- [ ] **Step 2: Add production-gate checks for the new frontend**

In `tests/test_production_gate.py`, after `TestNoLegacyStaticUI`, add:

```python
class TestFrontendStaticAssets:
    """The new Trust OS frontpage must exist without restoring legacy ui-chat."""

    def test_frontend_files_exist(self):
        from core.paths import PROJECT_ROOT

        frontend_dir = PROJECT_ROOT / "frontend"
        assert frontend_dir.exists(), "frontend/ directory missing"
        assert (frontend_dir / "index.html").exists(), "frontend/index.html missing"
        assert (frontend_dir / "styles.css").exists(), "frontend/styles.css missing"
        assert (frontend_dir / "app.js").exists(), "frontend/app.js missing"

    def test_frontend_does_not_use_legacy_branding(self):
        from core.paths import PROJECT_ROOT

        html = (PROJECT_ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        forbidden = ["Trading Terminal", "WAR ROOM", "ui-chat", "cassino"]
        for token in forbidden:
            assert token not in html, f"legacy UI language leaked into frontend: {token}"
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
pytest tests/test_agent_server_smoke.py tests/test_production_gate.py -q
```

Expected:

```text
FAIL tests/test_agent_server_smoke.py::test_agent_server_serves_core_endpoints
FAIL tests/test_production_gate.py::TestFrontendStaticAssets::test_frontend_files_exist
```

The failures should be because `/` still returns JSON and `frontend/` does not exist.

- [ ] **Step 4: Commit the failing tests**

```bash
git add tests/test_agent_server_smoke.py tests/test_production_gate.py
git commit -m "test(frontend): require trust os frontpage"
```

---

### Task 2: Serve The New Frontpage From FastAPI

**Files:**
- Modify: `src/agent_server/main.py`

- [ ] **Step 1: Add static serving imports**

At the top of `src/agent_server/main.py`, change:

```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
```

to:

```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
```

- [ ] **Step 2: Add the frontend directory constant**

After:

```python
ROOT_DIR = PROJECT_ROOT
```

add:

```python
FRONTEND_DIR = ROOT_DIR / "frontend"
```

- [ ] **Step 3: Mount `/frontend` when the directory exists**

Immediately after:

```python
app.include_router(a2a_router)
```

add:

```python
if FRONTEND_DIR.exists():
    app.mount(
        "/frontend",
        StaticFiles(directory=str(FRONTEND_DIR), html=False),
        name="frontend",
    )
else:
    logger.warning("[%s] Frontend directory not found at %s", AGENT_NAME, FRONTEND_DIR)
```

- [ ] **Step 4: Replace the root JSON response with HTML-first behavior**

Replace:

```python
@app.get("/")
async def root():
    return {
        "service": "SuperEzio API",
        "status": "ui_removed",
        "health": "/health",
        "manifest": "/product/manifest",
    }
```

with:

```python
@app.get("/")
async def root():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    return {
        "service": "SuperEzio API",
        "status": "frontend_missing",
        "health": "/health",
        "manifest": "/product/manifest",
    }
```

- [ ] **Step 5: Run the targeted smoke test and verify it still fails on missing files**

Run:

```bash
pytest tests/test_agent_server_smoke.py::test_agent_server_serves_core_endpoints -q
```

Expected:

```text
FAIL ... assert 'text/html' in 'application/json'
```

This confirms the fallback is working and the next task must create `frontend/index.html`.

- [ ] **Step 6: Commit server mounting**

```bash
git add src/agent_server/main.py
git commit -m "feat(frontend): serve trust os static shell"
```

---

### Task 3: Create The Semantic Frontpage HTML

**Files:**
- Create: `frontend/index.html`

- [ ] **Step 1: Create `frontend/index.html`**

Create the file with this complete content:

```html
<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SuperEzio Trust OS - Decisao financeira com alivio auditavel</title>
    <meta name="description" content="SuperEzio pesquisa, cruza evidencias, aponta riscos e transforma ruido de mercado em um proximo passo permitido.">
    <meta name="theme-color" content="#f6f7f3">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/frontend/styles.css">
    <script defer src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
    <script defer src="/frontend/app.js"></script>
  </head>
  <body>
    <a class="skip-link" href="#main">Pular para o conteudo</a>

    <header class="topbar" aria-label="Navegacao principal">
      <a class="brand" href="/" aria-label="SuperEzio Trust OS">
        <span class="brand-mark" aria-hidden="true">SE</span>
        <span>
          <strong>SuperEzio</strong>
          <small>Trust Operating System</small>
        </span>
      </a>

      <nav class="nav-tabs" aria-label="Areas do produto">
        <a href="#hoje" data-section-link="hoje" class="is-active">Hoje</a>
        <a href="#radar" data-section-link="radar">Radar</a>
        <a href="#decision-room" data-section-link="decision-room">Decision Room</a>
        <a href="#portfolio" data-section-link="portfolio">Portfolio</a>
        <a href="#diario" data-section-link="diario">Diario</a>
      </nav>

      <div class="system-pill" id="system-pill" aria-live="polite">
        <span class="status-dot status-dot--checking" id="system-dot"></span>
        <span id="system-label">Verificando motor</span>
      </div>
    </header>

    <main id="main">
      <section class="hero" aria-labelledby="hero-title">
        <div class="hero-copy">
          <p class="eyebrow">Seu mercado esta barulhento. Sua decisao nao precisa ser.</p>
          <h1 id="hero-title">Decisao financeira com alivio auditavel.</h1>
          <p class="hero-lede">SuperEzio pesquisa, cruza evidencias, aponta riscos e transforma ruido de mercado em um proximo passo permitido.</p>
          <div class="hero-actions">
            <a class="button button-primary" href="#decision-room">
              <i data-lucide="shield-check" aria-hidden="true"></i>
              Abrir Decision Room
            </a>
            <a class="button button-secondary" href="#radar">
              <i data-lucide="radar" aria-hidden="true"></i>
              Ver radar de hoje
            </a>
          </div>
        </div>

        <div class="product-preview" aria-label="Previa do produto SuperEzio">
          <section class="today-panel" id="hoje" aria-labelledby="today-title">
            <div class="panel-header">
              <span>Hoje</span>
              <span class="quiet-chip">3 itens importam</span>
            </div>
            <h2 id="today-title">O que merece sua atencao</h2>
            <div class="today-list" id="today-list">
              <article>
                <strong>SNDL</strong>
                <span>risco de liquidez e hype elevado</span>
              </article>
              <article>
                <strong>SOFI</strong>
                <span>dados suficientes para leitura completa</span>
              </article>
              <article>
                <strong>TLRY</strong>
                <span>aguardar volume confirmar o movimento</span>
              </article>
            </div>
          </section>

          <section class="decision-card" id="decision-room" aria-labelledby="decision-title">
            <div class="panel-header panel-header-dark">
              <span>Decision Room</span>
              <span class="audit-chip">AUDITED</span>
            </div>
            <div class="decision-main">
              <div>
                <p>SNDL hoje</p>
                <h2 id="decision-title">WAIT</h2>
              </div>
              <div class="confidence">
                <span>Confianca</span>
                <strong>61%</strong>
              </div>
            </div>
            <p class="decision-reason">Motivo: risco combinado alto, liquidez fraca e evidencia fundamental incompleta.</p>
            <div class="trust-stack" aria-label="Pilha de confianca">
              <span>14 evidencias</span>
              <span>8/12 consenso</span>
              <span>2 faltas</span>
            </div>
          </section>
        </div>
      </section>

      <section class="workflow" aria-label="Fluxo de decisao SuperEzio">
        <article id="radar">
          <i data-lucide="scan-search" aria-hidden="true"></i>
          <h2>Radar</h2>
          <p>Detecta sinais, anomalias e alertas sem transformar descoberta em urgencia.</p>
        </article>
        <article>
          <i data-lucide="door-open" aria-hidden="true"></i>
          <h2>Room</h2>
          <p>Separa pesquisa de acao: agora decidimos se existe um proximo passo permitido.</p>
        </article>
        <article id="portfolio">
          <i data-lucide="pie-chart" aria-hidden="true"></i>
          <h2>Portfolio</h2>
          <p>Leva em conta caixa, exposicao, horizonte e tolerancia antes de qualquer leitura.</p>
        </article>
        <article id="diario">
          <i data-lucide="book-check" aria-hidden="true"></i>
          <h2>Diario</h2>
          <p>Guarda motivo, evidencia e resultado para construir confianca ao longo do tempo.</p>
        </article>
      </section>

      <section class="principles" aria-labelledby="principles-title">
        <div>
          <p class="eyebrow">Trust Stack</p>
          <h2 id="principles-title">Nao e um placar magico de IA.</h2>
          <p>O SuperEzio mostra evidencias, consenso, conflitos, dados faltantes e restricoes de risco antes de sugerir qualquer acao permitida.</p>
        </div>
        <ul>
          <li><span></span>Evidencias verificaveis antes de conclusoes fortes.</li>
          <li><span></span>Dados ausentes favorecem STUDY_MORE ou WAIT.</li>
          <li><span></span>SpiderSense aparece como alerta, nao como teatro.</li>
          <li><span></span>Nao agir agora tambem pode ser a decisao correta.</li>
        </ul>
      </section>
    </main>
  </body>
</html>
```

- [ ] **Step 2: Run the root smoke test and verify partial progress**

Run:

```bash
pytest tests/test_agent_server_smoke.py::test_agent_server_serves_core_endpoints -q
```

Expected:

```text
FAIL ... /frontend/app.js status_code == 404
```

Root should now be HTML, but CSS/JS are still missing.

- [ ] **Step 3: Commit HTML shell**

```bash
git add frontend/index.html
git commit -m "feat(frontend): add trust os html shell"
```

---

### Task 4: Add The Trust OS Visual System

**Files:**
- Create: `frontend/styles.css`

- [ ] **Step 1: Create `frontend/styles.css`**

Create the file with this complete content:

```css
:root {
  color-scheme: light;
  --bg: #f6f7f3;
  --surface: #ffffff;
  --surface-soft: #eef2ea;
  --ink: #172018;
  --muted: #5e6a5c;
  --line: #dbe2d5;
  --line-strong: #c7d1c0;
  --dark: #101711;
  --dark-line: #2a352b;
  --verified: #d8eb83;
  --caution: #df9467;
  --data: #91b9e9;
  --radius: 14px;
  --shadow: 0 24px 80px rgba(23, 32, 24, 0.12);
}

* {
  box-sizing: border-box;
}

html {
  scroll-behavior: smooth;
}

body {
  margin: 0;
  min-width: 320px;
  background: var(--bg);
  color: var(--ink);
  font-family: "Manrope", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  letter-spacing: 0;
}

a {
  color: inherit;
  text-decoration: none;
}

.skip-link {
  position: fixed;
  top: 12px;
  left: 12px;
  z-index: 30;
  transform: translateY(-140%);
  border: 1px solid var(--ink);
  border-radius: 8px;
  background: var(--surface);
  padding: 8px 10px;
}

.skip-link:focus {
  transform: translateY(0);
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 20px;
  border-bottom: 1px solid rgba(219, 226, 213, 0.9);
  background: rgba(246, 247, 243, 0.86);
  padding: 14px clamp(16px, 4vw, 40px);
  backdrop-filter: blur(18px);
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.brand-mark {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 8px;
  background: var(--ink);
  color: var(--surface);
  font-size: 12px;
  font-weight: 700;
}

.brand strong,
.brand small {
  display: block;
}

.brand strong {
  font-size: 15px;
}

.brand small {
  color: var(--muted);
  font-size: 11px;
}

.nav-tabs {
  display: flex;
  justify-content: center;
  gap: 6px;
}

.nav-tabs a {
  min-height: 34px;
  border-radius: 8px;
  padding: 8px 10px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 600;
}

.nav-tabs a:hover,
.nav-tabs a:focus-visible,
.nav-tabs a.is-active {
  background: var(--ink);
  color: var(--surface);
  outline: none;
}

.system-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface);
  padding: 7px 10px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--caution);
}

.status-dot--ok {
  background: #6aa86c;
}

.status-dot--down {
  background: #c86161;
}

.hero {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(420px, 1.05fr);
  gap: clamp(24px, 5vw, 64px);
  align-items: center;
  min-height: calc(100vh - 68px);
  padding: clamp(36px, 7vw, 92px) clamp(16px, 4vw, 48px) 28px;
}

.hero-copy {
  max-width: 680px;
}

.eyebrow {
  margin: 0 0 14px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 700;
}

h1 {
  margin: 0;
  max-width: 780px;
  font-size: clamp(44px, 7vw, 92px);
  font-weight: 700;
  letter-spacing: -0.04em;
  line-height: 0.94;
}

.hero-lede {
  max-width: 560px;
  margin: 22px 0 0;
  color: var(--muted);
  font-size: clamp(16px, 2vw, 19px);
  line-height: 1.55;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 28px;
}

.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 44px;
  border-radius: 10px;
  padding: 11px 14px;
  font-size: 14px;
  font-weight: 700;
}

.button svg,
.workflow svg {
  width: 18px;
  height: 18px;
  stroke-width: 1.5;
}

.button-primary {
  background: var(--ink);
  color: var(--surface);
}

.button-secondary {
  border: 1px solid var(--line);
  background: var(--surface);
}

.button:focus-visible {
  outline: 3px solid rgba(145, 185, 233, 0.45);
  outline-offset: 2px;
}

.product-preview {
  display: grid;
  grid-template-columns: minmax(0, 0.86fr) minmax(0, 1.14fr);
  gap: 14px;
  border: 1px solid var(--line);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.58);
  padding: 14px;
  box-shadow: var(--shadow);
}

.today-panel,
.decision-card {
  min-height: 340px;
  border-radius: var(--radius);
  padding: 18px;
}

.today-panel {
  border: 1px solid var(--line);
  background: var(--surface);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}

.quiet-chip,
.audit-chip {
  white-space: nowrap;
  border-radius: 999px;
  padding: 5px 8px;
  font-size: 10px;
}

.quiet-chip {
  background: var(--surface-soft);
}

.today-panel h2,
.principles h2 {
  margin: 16px 0;
  font-size: clamp(22px, 2.6vw, 34px);
  letter-spacing: -0.035em;
  line-height: 1.03;
}

.today-list {
  display: grid;
  gap: 10px;
  margin-top: 18px;
}

.today-list article {
  min-height: 58px;
  border: 1px solid #e7ece2;
  border-radius: 11px;
  padding: 10px;
}

.today-list strong,
.today-list span {
  display: block;
}

.today-list strong {
  font-family: "JetBrains Mono", monospace;
  font-size: 12px;
}

.today-list span {
  margin-top: 5px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.35;
}

.decision-card {
  border: 1px solid var(--dark-line);
  background: var(--dark);
  color: #f5f8ef;
}

.panel-header-dark {
  color: #b9c8b6;
}

.audit-chip {
  border: 1px solid rgba(216, 235, 131, 0.44);
  color: var(--verified);
}

.decision-main {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 18px;
  margin-top: 28px;
}

.decision-main p,
.confidence span {
  margin: 0;
  color: #bbc8b8;
  font-size: 12px;
}

.decision-main h2 {
  margin: 6px 0 0;
  font-size: clamp(44px, 6vw, 68px);
  letter-spacing: -0.05em;
  line-height: 0.9;
}

.confidence {
  text-align: right;
}

.confidence strong {
  display: block;
  margin-top: 4px;
  font-family: "JetBrains Mono", monospace;
  font-size: 24px;
}

.decision-reason {
  margin: 24px 0 0;
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.06);
  padding: 13px;
  color: #dce7d7;
  font-size: 13px;
  line-height: 1.45;
}

.trust-stack {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-top: 12px;
}

.trust-stack span {
  min-height: 46px;
  border-radius: 10px;
  padding: 10px 8px;
  font-size: 11px;
}

.trust-stack span:nth-child(1) {
  background: rgba(216, 235, 131, 0.13);
}

.trust-stack span:nth-child(2) {
  background: rgba(145, 185, 233, 0.13);
}

.trust-stack span:nth-child(3) {
  background: rgba(223, 148, 103, 0.15);
}

.workflow {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  margin: 0 clamp(16px, 4vw, 48px) 48px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--line);
}

.workflow article {
  min-height: 180px;
  background: var(--surface);
  padding: 18px;
}

.workflow h2 {
  margin: 14px 0 8px;
  font-size: 20px;
  letter-spacing: -0.025em;
}

.workflow p,
.principles p,
.principles li {
  color: var(--muted);
  font-size: 14px;
  line-height: 1.5;
}

.principles {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(320px, 1.1fr);
  gap: 32px;
  align-items: start;
  margin: 0 clamp(16px, 4vw, 48px) 64px;
  border-top: 1px solid var(--line);
  padding-top: 42px;
}

.principles ul {
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.principles li {
  display: grid;
  grid-template-columns: 10px 1fr;
  gap: 10px;
  align-items: start;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
  padding: 13px;
}

.principles li span {
  width: 8px;
  height: 8px;
  margin-top: 6px;
  border-radius: 50%;
  background: var(--verified);
}

@media (max-width: 980px) {
  .topbar {
    grid-template-columns: 1fr auto;
  }

  .nav-tabs {
    grid-column: 1 / -1;
    justify-content: flex-start;
    overflow-x: auto;
    padding-bottom: 2px;
  }

  .hero,
  .principles {
    grid-template-columns: 1fr;
  }

  .product-preview,
  .workflow {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 640px) {
  .topbar {
    gap: 12px;
  }

  .system-pill {
    justify-self: end;
    max-width: 155px;
  }

  .hero {
    padding-top: 30px;
  }

  .product-preview,
  .workflow,
  .trust-stack {
    grid-template-columns: 1fr;
  }

  .today-panel,
  .decision-card {
    min-height: auto;
  }

  .decision-main {
    align-items: flex-start;
  }
}
```

- [ ] **Step 2: Run production-gate asset tests**

Run:

```bash
pytest tests/test_production_gate.py::TestFrontendStaticAssets -q
```

Expected:

```text
FAIL ... frontend/app.js missing
```

The CSS should now exist, but JS is still intentionally missing.

- [ ] **Step 3: Commit styles**

```bash
git add frontend/styles.css
git commit -m "feat(frontend): add trust os visual system"
```

---

### Task 5: Add Frontpage Behavior And Safe Data Hooks

**Files:**
- Create: `frontend/app.js`

- [ ] **Step 1: Create `frontend/app.js`**

Create the file with this complete content:

```javascript
(function initializeSuperEzioFrontpage() {
  const systemDot = document.getElementById("system-dot");
  const systemLabel = document.getElementById("system-label");
  const sectionLinks = Array.from(document.querySelectorAll("[data-section-link]"));

  function setSystemState(state, label) {
    if (!systemDot || !systemLabel) return;
    systemDot.classList.remove("status-dot--checking", "status-dot--ok", "status-dot--down");
    systemDot.classList.add(state === "ok" ? "status-dot--ok" : "status-dot--down");
    systemLabel.textContent = label;
  }

  async function fetchJson(path) {
    const response = await fetch(path, { headers: { Accept: "application/json" } });
    if (!response.ok) {
      throw new Error(`${path} returned ${response.status}`);
    }
    return response.json();
  }

  async function hydrateStatus() {
    try {
      const health = await fetchJson("/health");
      const manifest = await fetchJson("/product/manifest");
      const productName = manifest.product?.product_name || manifest.product_name || "SuperEzio";
      const status = health.status === "ok" ? "Motor online" : "Motor limitado";
      setSystemState("ok", `${productName}: ${status}`);
    } catch (error) {
      setSystemState("down", "Motor indisponivel");
      console.info("SuperEzio frontpage running in offline-safe mode:", error.message);
    }
  }

  function wireActiveNavigation() {
    if (!sectionLinks.length) return;
    const sections = sectionLinks
      .map((link) => document.getElementById(link.getAttribute("data-section-link")))
      .filter(Boolean);

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (!visible) return;
        sectionLinks.forEach((link) => {
          link.classList.toggle(
            "is-active",
            link.getAttribute("data-section-link") === visible.target.id,
          );
        });
      },
      { threshold: [0.24, 0.5, 0.75] },
    );

    sections.forEach((section) => observer.observe(section));
  }

  function wireKeyboardFocus() {
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      const active = document.activeElement;
      if (active && typeof active.blur === "function") {
        active.blur();
      }
    });
  }

  function bootIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons({ attrs: { "stroke-width": 1.5 } });
    }
  }

  hydrateStatus();
  wireActiveNavigation();
  wireKeyboardFocus();
  bootIcons();
})();
```

- [ ] **Step 2: Run all frontend-related tests**

Run:

```bash
pytest tests/test_agent_server_smoke.py tests/test_production_gate.py -q
```

Expected:

```text
26 passed
```

- [ ] **Step 3: Commit JS behavior**

```bash
git add frontend/app.js
git commit -m "feat(frontend): add trust os runtime hooks"
```

---

### Task 6: Verify The Frontpage End To End

**Files:**
- Modify: no product files unless verification reveals a concrete bug

- [ ] **Step 1: Run the core frontend/server test set**

Run:

```bash
pytest tests/test_agent_server_smoke.py tests/test_production_gate.py tests/test_pipeline_e2e.py -q
```

Expected:

```text
36 passed
```

- [ ] **Step 2: Start the local server**

Run:

```bash
powershell -ExecutionPolicy Bypass -File scripts/launch_superezio_ceo.ps1 -SkipCEO
```

Expected:

```text
API: http://127.0.0.1:8002
Health: http://127.0.0.1:8002/health
```

If that launcher is inconvenient, run:

```bash
$env:PYTHONPATH="src"; python -m uvicorn agent_server.main:app --host 127.0.0.1 --port 8002
```

- [ ] **Step 3: Browser verification**

Open:

```text
http://127.0.0.1:8002/
```

Verify manually:

- The first screen shows "SuperEzio Trust OS".
- The hero says "Decisao financeira com alivio auditavel."
- The five destinations are visible.
- The Decision Room panel is dark and readable.
- The browser console has no JavaScript errors.
- Narrow the browser to about 375px and verify no text overlaps.

- [ ] **Step 4: Optional Playwright screenshot check**

If Playwright is installed, run this from the repo root:

```bash
node -e "const { chromium } = require('playwright'); (async () => { const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1280, height: 900 } }); await p.goto('http://127.0.0.1:8002/', { waitUntil: 'networkidle' }); await p.screenshot({ path: 'logs/frontpage-desktop.png', fullPage: true }); await p.setViewportSize({ width: 375, height: 812 }); await p.screenshot({ path: 'logs/frontpage-mobile.png', fullPage: true }); console.log(await p.title()); await b.close(); })();"
```

Expected:

```text
SuperEzio Trust OS - Decisao financeira com alivio auditavel
```

- [ ] **Step 5: Commit any verification fixes**

If verification required no product changes, do not create a commit. If a concrete bug was fixed, commit only the touched files:

```bash
git add frontend src/agent_server/main.py tests/test_agent_server_smoke.py tests/test_production_gate.py
git commit -m "fix(frontend): polish trust os frontpage verification"
```

---

## Self-Review

Spec coverage:

- Calm Institutional base: Task 4 visual system.
- SaaS Operational structure: Task 3 nav/workflow markup and Task 4 layout.
- Premium Dark Decision Room: Task 3 decision card and Task 4 dark panel styling.
- Five destinations: Task 3 markup and Task 5 navigation behavior.
- Serve as first screen: Task 2 FastAPI root behavior.
- Avoid old terminal UI: Task 1 production-gate test and Task 3 copy.
- Error handling/offline state: Task 5 health fallback.
- Accessibility/responsiveness: Task 3 semantic HTML, Task 4 responsive/focus CSS, Task 6 manual verification.
- No live recommendation implication: Task 3 sample uses static illustrative decision preview only.

Placeholder scan:

- No `TBD`, `TODO`, or "fill in later" steps.
- Every code-changing step includes concrete code.
- Every test step includes exact commands and expected results.

Type consistency:

- `FRONTEND_DIR` is defined in `src/agent_server/main.py` before use.
- `/frontend/app.js` contains `initializeSuperEzioFrontpage`, matching the smoke test assertion.
- IDs used by `frontend/app.js` exist in `frontend/index.html`.
