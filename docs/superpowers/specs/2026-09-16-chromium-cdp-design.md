# SuperEzio — spec: Chromium compilado + CDP, sem Playwright

**Data:** 16 de Setembro de 2026  
**Estado:** desenho fechado em conversa; à espera de revisão do operador antes do plano de implementação  
**Repo:** SuperEzio  
**Abordagem:** B (compile + CDP). Playwright sai do `pyproject.toml`.

## 1. Trabalho deste ciclo

A suíte browser não depende do cache `cursor-sandbox-cache` nem de `python -m playwright install`.

| Peça | O que fica pronto |
|---|---|
| Motor | Chromium compilado nesta máquina (`C:\src\chromium`), não Chrome-for-Testing, não Chrome do sistema |
| Driver | Fachada CDP nossa (`core.browser`) — WebSocket DevTools. Sem pacote `playwright` |
| Aceite | Os testes que hoje importam Playwright passam a CDP; os 5 vermelhos (smoke final answer + portfolio) verdes quando o exe existe |
| Falta de binário | **skip** com razão explícita — `--maxfail=5` não corta a suíte com 5 erros iguais |

Scripts operacionais (`scripts/browser_smoke.py` e restantes) **não** migram neste ciclo. Remover `playwright` do `pyproject` implica que esses scripts só correm depois da vaga 2, ou com extra opcional — **neste ciclo o extra some**. Scripts que importam Playwright quebram até a vaga 2. Isso é aceite explícito.

Não se faz: WebView2, Electron como motor de teste, `PLAYWRIGHT_BROWSERS_PATH`, `channel="chrome"`.

## 2. Onde vive o quê

```text
C:\src\chromium\                 # source + out/  — FORA do git SuperEzio
  depot_tools\
  src\                           # checkout Chromium
  src\out\SuperEzio\             # ninja: chrome.exe, chrome-headless-shell.exe

C:\Users\marco\Desktop\SuperEzio\
  runtime\browser\manifest.json  # versionado: revisão git, gn args hash, sha256 dos exe
  runtime\browser\out\           # gitignored: cópia dos dois exe (+ DLLs necessárias)
  scripts\build_chromium.ps1     # versionado: gn+ninja+copy+hash
  src\core\browser\              # launch + cliente CDP
```

`.gitignore`: `runtime/browser/out/`. O source em `C:\src\chromium` nunca entra no repo.

## 3. Contratos

### 3.1 `core.browser`

```python
class BrowserUnavailableError(Exception): ...

def resolve_browser(*, mode: str) -> Path:
    """mode in {"headless", "headed"}. Path sob runtime/browser/out/."""

def launch_browser(*, headless: bool = True) -> Browser:
    """Sobe o processo, lê DevToolsActivePort, liga WebSocket CDP."""

@dataclass
class Browser:
    proc: subprocess.Popen
    ws_url: str
    def new_page(self) -> Page: ...
    def close(self) -> None: ...

class Page:
    def set_content(self, html: str) -> None: ...
    def evaluate(self, expression: str, arg: object = None) -> object: ...
    def click(self, selector: str) -> None: ...
    def fill(self, selector: str, text: str) -> None: ...
    def content(self) -> str: ...
    def wait_for_function(self, expression: str, *, timeout_ms: int) -> None: ...
```

Timeouts: o equivalente a `PlaywrightTimeoutError` é `core.browser.TimeoutError`. Os testes que hoje `pytest.raises(PlaywrightTimeoutError)` passam a `pytest.raises(TimeoutError)` desta fachada.

API mínima = o que os 5 ficheiros de teste usam hoje. Sem locator engine, sem network intercept, sem tracing. Se um teste precisar de mais, acrescenta-se o método com teste, não se reimporta Playwright.

### 3.2 Launch do processo

```
chrome-headless-shell.exe --remote-debugging-port=0 --user-data-dir=<tmp> --no-first-run
```

Headed: `chrome.exe` com os mesmos flags menos headless.

`remote-debugging-port=0` → ler `DevToolsActivePort` no user-data-dir. Sem porta fixa (colide com o Ezio :8002 / Mike :8083).

### 3.3 Pytest

- Marker `browser` em `pytest.ini`.
- Fixture session `browser_runtime`: se `resolve_browser` falhar → **skip** de todos os itens `browser` com `Chromium SuperEzio ausente: scripts/build_chromium.ps1`.
- Fixture function `browser_page`: `launch_browser` → `new_page` → teardown `close()`.
- Ficheiros que **hoje** importam Playwright (todos têm de deixar de o fazer, senão remover o pacote parte a collection):

  - `tests/test_browser_smoke_final_answer.py`
  - `tests/test_client_portfolio_browser.py`
  - `tests/test_td_research_browser.py`
  - `tests/test_electron_installed.py` — CDP para o **Electron do produto** continua; deixa de usar `playwright` para ligar. Se o Electron não estiver, skip (já é o espírito do ficheiro).
  - `tests/e2e/test_browser_full_flow.py`

- `conftest.py` **não** importa Playwright no topo. `scripts.browser_smoke` só entra na fixture que o chama; essa fixture skipa se o script ainda for Playwright e o pacote tiver saído.

### 3.4 Compile

Alvo gn (release, sem símbolos): `chrome` e `headless_shell`.  
Não se usa a RTX 2070 no compile.  
`scripts/build_chromium.ps1` falha com erro real se `depot_tools` / VS Build Tools / checkout faltarem — nunca finge sucesso.

Revisão Chromium pinada no `manifest.json`. Subir revisão = bump do manifest + rebuild + novos SHA256.

## 4. Fora deste ciclo

- Migrar scripts operacionais para CDP
- Compilar Ungoogled / fork de UI
- Perspective, Heart panel browser, MCP Playwright do Cursor
- Tirar `--maxfail=5` (fica; o skip resolve o buraco browser)

## 5. Aceite

1. `playwright` não está em `pyproject.toml` / lock.
2. Nenhum ficheiro sob `tests/` faz `import playwright`.
3. Com `runtime/browser/out/chrome-headless-shell.exe` presente:  
   `pytest tests/test_browser_smoke_final_answer.py tests/test_client_portfolio_browser.py -q` → **PASS**.
4. Sem o exe: os testes `browser` **SKIP**, o resto da suíte corre, collection sem ERROR.
5. `scripts/build_chromium.ps1 -Help` documenta depot_tools, gn args e o copy para `runtime/browser/out`.

## 6. Limitação declarada (não é bug)

A primeira compile nesta máquina pode levar **dias a semanas** e ~100 GB em `C:\src\chromium`. Até o exe existir, a suíte browser é skip, não verde. Skip ≠ conserto do motor; é o portão honesto enquanto o ninja corre.
