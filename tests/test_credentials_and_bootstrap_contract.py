"""Contrato de credenciais do bootstrap.

Estático por design: NUNCA executa setup_superezio.sh nem os probes de
scripts/ (eles sobem o runtime ou batem em endpoints live). Garante que a
arvore ativa nao contem senha conhecida/default hardcoded e que toda fonte de
credencial e leitura obrigatoria de ambiente (fail-closed).

Se este contrato falhar, a diferenca deve ser resolvida por um humano antes de
qualquer merge: senhas conhecidas em texto na arvore sao vetor de reuso.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_PATH = REPO_ROOT / "setup_superezio.sh"
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Probes de login ao vivo que usavam a senha real do operador hardcoded.
LOGIN_PROBES = [
    "capture_live_state.py",
    "capture_ui_improvements.py",
    "deep_interactive_user_test.py",
    "open_real_visible_browser.py",
    "test_bob_chat_step.py",
    "verify_analyze_with_bob_button.py",
    "verify_live_browser.py",
    "verify_live_greeting_browser.py",
]

KNOWN_PASSWORDS = ["SuperEzioAdmin2024!", "Marco1234!"]
ENV_VAR = "SUPEREZIO_ADMIN_PASSWORD"


def _read_text(path: Path) -> str:
    assert path.is_file(), f"arquivo obrigatorio ausente: {path}"
    return path.read_text(encoding="utf-8")


def _setup_text() -> str:
    return _read_text(SETUP_PATH)


def _function_body(text: str, name: str) -> str:
    """Fatia estatica do corpo de `name() { ... }` para checagens locais."""
    start = re.search(rf"^{re.escape(name)}\(\) \{{", text, flags=re.MULTILINE)
    assert start is not None, f"funcao {name}() ausente no setup"
    depth = 0
    for i, line in enumerate(text[start.start() :].splitlines()):
        depth += line.count("{") - line.count("}")
        if depth == 0:
            return "\n".join(text[start.start() :].splitlines()[: i + 1])
    raise AssertionError(f"funcao {name}() sem fechamento de chave no setup")


def test_setup_nao_contem_senha_default_conhecida() -> None:
    text = _setup_text()
    assert "SuperEzioAdmin2024!" not in text


def test_setup_nao_tem_fallback_para_admin_pass() -> None:
    text = _setup_text()
    for line in text.splitlines():
        # Atribuicao de ADMIN_PASS derivada de env com default nao-vazio.
        assert not re.search(r"ADMIN_PASS\s*=.*SUPEREZIO_ADMIN_PASSWORD\s*:-", line), (
            f"fallback de senha para ADMIN_PASS encontrado: {line.strip()}"
        )
        # Qualquer expansao ${SUPEREZIO_ADMIN_PASSWORD:-<default>} nao-vazio.
        assert not re.search(r"SUPEREZIO_ADMIN_PASSWORD:-(?!\})", line), (
            f"expansao com default nao-vazio encontrada: {line.strip()}"
        )


def test_setup_exige_env_e_ensina_geracao_fail_closed() -> None:
    text = _setup_text()
    seed = _function_body(text, "step_seed_admin")
    # (c) mensagem de exigencias da variavel + geracao via token_hex.
    assert ENV_VAR in seed
    assert "token_hex" in text
    assert re.search(r"required but not set", seed, flags=re.IGNORECASE) or "nao definida" in seed
    # Guarda fail-closed: sem a env, o passo nao chega a semear admin.
    assert re.search(r"-z \"\$\{SUPEREZIO_ADMIN_PASSWORD:-\}\"", seed), (
        "guarda de variavel ausente no step_seed_admin"
    )
    # Erros acumulados abortam o script com exit != 0 (fail-closed no final).
    summary = _function_body(text, "summary")
    assert re.search(r"exit 1", summary), "summary precisa sair com exit 1 quando ERR_COUNT > 0"


def test_scripts_sem_literais_de_senha() -> None:
    # (b) grep recursivo em scripts/: zero ocorrencias.
    candidates = list(SCRIPTS_DIR.rglob("*.py"))
    assert candidates, "nenhum script encontrado em scripts/"
    for script in candidates:
        content = script.read_text(encoding="utf-8")
        for literal in KNOWN_PASSWORDS:
            assert literal not in content, f"senha conhecida em {script}"


def test_cada_probe_le_credencial_do_ambiente() -> None:
    # (d) cada probe referencia a fonte via env e nao contem literal.
    for name in LOGIN_PROBES:
        text = _read_text(SCRIPTS_DIR / name)
        assert f'os.environ.get("{ENV_VAR}")' in text, f"{name} nao le {ENV_VAR} do ambiente"
        assert re.search(r"password\s*=\s*os\.environ\.get", text), (
            f"{name} nao atribui a senha a partir do ambiente"
        )
        for literal in KNOWN_PASSWORDS:
            assert literal not in text, f"senha conhecida em scripts/{name}"
        # O corpo do POST usa a variavel, nunca um literal.
        assert re.search(r'"password"\s*:\s*password', text), (
            f"{name} nao envia a senha via variavel no login"
        )
        # Fail-closed: sem a env, o probe aborta com mensagem clara.
        assert re.search(r"if not password:", text), f"{name} nao valida a env antes do login"
        assert re.search(r"raise SystemExit", text), f"{name} nao aborta sem a env"
