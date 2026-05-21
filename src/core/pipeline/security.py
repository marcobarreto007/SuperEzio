"""
Pipeline Security â€” Input Validation, Sanitization & Rate Limiting
===================================================================
Centraliza todas as verificaÃ§Ãµes de seguranÃ§a para o pipeline:
  - Input validation (tamanho, caracteres, injeÃ§Ã£o)
  - Rate limiting por sessÃ£o/IP
  - Output filtering (PII, forbidden phrases)
  - Request ID tracing auto-increment

Runtime note:`r`n    ``sanitize_output`` is active in the production pipeline. The remaining`r`n    validators stay available for explicit integration through future gates.
"""

from __future__ import annotations

import re
import time
import uuid
import hashlib
from typing import Dict, List, Optional
from threading import Lock
from collections import defaultdict

from core.security.constants import FORBIDDEN_OUTPUT_PHRASES

from ..observability.neural_log import log_event
from ..observability.debug_logger import debug_logger, MODULE_SECURITY
from ..model_serving.sanitizer import strip_private_model_channels

# â”€â”€ Constants â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

MAX_MESSAGE_LENGTH = 10_000  # caracteres mÃ¡ximos por mensagem
MAX_CONTEXT_LENGTH = 100_000  # caracteres mÃ¡ximos para contexto
MAX_OUTPUT_LENGTH = 50_000  # caracteres mÃ¡ximos de output
RATE_LIMIT_WINDOW_S = 60.0  # janela de rate limiting (segundos)
RATE_LIMIT_MAX_CALLS = 30  # mÃ¡ximo de chamadas por janela

# Caracteres / padrÃµes proibidos (injeÃ§Ã£o)
FORBIDDEN_PATTERNS: List[str] = [
    r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>",  # XSS
    r"javascript:",  # XSS href
    r"on\w+\s*=",  # event handlers
    r"SELECT\s+.*\s+FROM",  # SQL injection (case insensitive match)
    r"DROP\s+TABLE",
    r"UNION\s+.*\s+SELECT",
    r"exec\s*\(.*\)",
    r"eval\s*\(.*\)",
    r"system\s*\(",
    r"__import__\s*\(",
    r"os\.system",
    r"subprocess",
    r"base64\s*\(.*\)",
]

# PII patterns (para filtering de output)
PII_PATTERNS: Dict[str, str] = {
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "cpf": r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",
    "cnpj": r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b",
    "cep": r"\b\d{5}-?\d{3}\b",
    "credit_card": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
    "phone": r"(?<!\d)(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?\d{4,5}[-.\s]?\d{4}(?!\d)",
    "ip": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
}

# â”€â”€ Global State â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_request_id_counter: int = 0
_request_id_lock: Lock = Lock()

# Rate limiting state
_rate_limit_store: Dict[str, List[float]] = defaultdict(list)
_rate_limit_lock: Lock = Lock()

# â”€â”€ Core Functions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def generate_request_id() -> str:
    """
    Gera um request_id Ãºnico e sequencial para tracing.
    Formato: REQ-{sequencial}-{hash curto}
    """
    global _request_id_counter
    with _request_id_lock:
        _request_id_counter += 1
        seq = _request_id_counter
    short_hash = uuid.uuid4().hex[:6].upper()
    return f"REQ-{seq:05d}-{short_hash}"


def validate_input(message: str, context: str = "") -> Optional[str]:
    """
    Valida entrada do usuÃ¡rio. Retorna None se OK, ou string de erro se rejeitado.

    Checks:
      1. Tamanho da mensagem
      2. Tamanho do contexto
      3. PadrÃµes de injeÃ§Ã£o (XSS, SQL, code execution)
      4. Caracteres nulos / invÃ¡lidos
    """
    if not message or not message.strip():
        debug_logger.debug(MODULE_SECURITY, "validate_input: empty message rejected")
        return "INPUT_REJECTED: mensagem vazia."

    msg_len = len(message)
    debug_logger.trace(MODULE_SECURITY, "validate_input: checking", message_length=msg_len)

    if msg_len > MAX_MESSAGE_LENGTH:
        debug_logger.warn(MODULE_SECURITY, "INPUT_TOO_LONG", length=msg_len, max=MAX_MESSAGE_LENGTH)
        log_event(
            "SECURITY",
            "INPUT_TOO_LONG",
            {
                "length": msg_len,
                "max": MAX_MESSAGE_LENGTH,
            },
        )
        return f"INPUT_REJECTED: mensagem excede {MAX_MESSAGE_LENGTH} caracteres ({msg_len})."

    if context and len(context) > MAX_CONTEXT_LENGTH:
        debug_logger.warn(
            MODULE_SECURITY,
            "CONTEXT_TOO_LONG",
            length=len(context),
            max=MAX_CONTEXT_LENGTH,
        )
        log_event(
            "SECURITY",
            "CONTEXT_TOO_LONG",
            {
                "length": len(context),
                "max": MAX_CONTEXT_LENGTH,
            },
        )
        return f"INPUT_REJECTED: contexto excede {MAX_CONTEXT_LENGTH} caracteres."

    # Null bytes
    if "\x00" in message or (context and "\x00" in context):
        log_event("SECURITY", "NULL_BYTES_DETECTED", {})
        return "INPUT_REJECTED: entrada contÃ©m bytes nulos."

    # PadrÃµes de injeÃ§Ã£o
    combined = f"{message} {context if context else ''}"
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            log_event(
                "SECURITY",
                "INJECTION_DETECTED",
                {
                    "pattern": pattern[:50],
                },
            )
            return "INPUT_REJECTED: padrÃ£o de injeÃ§Ã£o detectado."

    # Caracteres de controle (exceto newline/tab)
    control_chars = re.findall(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", combined)
    if control_chars:
        log_event(
            "SECURITY",
            "CONTROL_CHARS_DETECTED",
            {
                "chars": [hex(ord(c)) for c in set(control_chars)],
            },
        )
        return "INPUT_REJECTED: control characters are not allowed."

    return None  # OK


def check_rate_limit(
    session_id: str = "default",
    max_calls: int = RATE_LIMIT_MAX_CALLS,
    window_s: float = RATE_LIMIT_WINDOW_S,
) -> Optional[str]:
    """
    Verifica rate limiting para uma sessÃ£o.
    Retorna None se OK, ou mensagem de erro se excedeu.
    """
    now = time.time()
    window_start = now - window_s

    with _rate_limit_lock:
        # Limpar entradas antigas
        timestamps = _rate_limit_store[session_id]
        _rate_limit_store[session_id] = [t for t in timestamps if t > window_start]

        # Verificar
        if len(_rate_limit_store[session_id]) >= max_calls:
            log_event(
                "SECURITY",
                "RATE_LIMIT_EXCEEDED",
                {
                    "session": session_id,
                    "calls": len(_rate_limit_store[session_id]),
                    "window_s": window_s,
                },
            )
            return f"RATE_LIMITED: mÃ¡ximo de {max_calls} chamadas a cada {window_s:.0f}s. Aguarde."

        _rate_limit_store[session_id].append(now)

    return None  # OK


def sanitize_output(text: str) -> str:
    """
    Sanitiza o output do LLM:
      1. Remove/Filtra PII
      2. Verifica frases proibidas (log + marcaÃ§Ã£o)
      3. Trunca se muito longo

    Returns:
        Texto sanitizado
    """
    if not text:
        return text

    original = text
    text = strip_private_model_channels(text)

    # 1. Filtrar PII (substituir por [REDACTED])
    for pii_name, pattern in PII_PATTERNS.items():
        text = re.sub(pattern, f"[REDACTED:{pii_name}]", text)

    # 2. Verificar frases proibidas (log + marcaÃ§Ã£o no output)
    text_lower = text.lower()
    found_forbidden = [p for p in FORBIDDEN_OUTPUT_PHRASES if p in text_lower]
    if found_forbidden:
        log_event(
            "SECURITY",
            "FORBIDDEN_PHRASE_OUTPUT",
            {
                "phrases": found_forbidden,
            },
        )
        text += "\n\n[SYSTEM] STAFF+ENGINEER MODE ACTIVE. No investment has a guaranteed return."

    # 3. Truncar se muito longo
    if len(text) > MAX_OUTPUT_LENGTH:
        log_event(
            "SECURITY",
            "OUTPUT_TRUNCATED",
            {
                "original_length": len(original),
                "truncated_to": MAX_OUTPUT_LENGTH,
            },
        )
        text = text[:MAX_OUTPUT_LENGTH] + "\n\n[TRUNCATED: output excede limite de seguranÃ§a]"

    return text


def hash_session_id(session_id: str) -> str:
    """Hash seguro de session_id para rate limiting (nÃ£o expÃµe IDs reais)."""
    return hashlib.sha256(session_id.encode()).hexdigest()[:16]


# â”€â”€ Pipeline-Wide Security Context â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class SecurityContext:
    """
    Contexto de seguranÃ§a para uma requisiÃ§Ã£o do pipeline.
    Gerencia request_id, validaÃ§Ã£o, rate limit e sanitizaÃ§Ã£o.

    Uso:
        sec = SecurityContext(message, session_id="user123")
        if sec.error:
            return sec.error
        # ... processamento ...
        safe_output = sec.sanitize(llm_output)
    """

    def __init__(
        self,
        message: str,
        context: str = "",
        session_id: str = "default",
        skip_rate_limit: bool = False,
    ) -> None:
        self.request_id = generate_request_id()
        self.message = message
        self.context = context
        self.session_id = session_id
        self.error: Optional[str] = None
        self.pii_detected: bool = False

        # 1. Validar input
        validation_error = validate_input(message, context)
        if validation_error:
            self.error = validation_error
            log_event(
                "SECURITY",
                "INPUT_REJECTED",
                {
                    "request_id": self.request_id,
                    "reason": validation_error,
                },
            )
            return

        # 2. Rate limit (a menos que explicitamente ignorado)
        if not skip_rate_limit:
            rate_error = check_rate_limit(session_id)
            if rate_error:
                self.error = rate_error
                log_event(
                    "SECURITY",
                    "RATE_LIMITED",
                    {
                        "request_id": self.request_id,
                        "session": session_id,
                    },
                )
                return

        # 3. Detect PII na entrada (para log)
        combined = f"{message} {context if context else ''}"
        for pii_name, pattern in PII_PATTERNS.items():
            if re.search(pattern, combined):
                self.pii_detected = True
                log_event(
                    "SECURITY",
                    "PII_IN_INPUT",
                    {
                        "request_id": self.request_id,
                        "pii_type": pii_name,
                    },
                )
                break

        log_event(
            "SECURITY",
            "CONTEXT_INIT",
            {
                "request_id": self.request_id,
                "session": hash_session_id(session_id),
                "msg_length": len(message),
                "pii_detected": self.pii_detected,
            },
        )

    def sanitize(self, text: str) -> str:
        """Sanitiza output e adiciona request_id metadata se disponÃ­vel."""
        safe = sanitize_output(text)
        if self.request_id:
            safe += f"\n\n[request_id: {self.request_id}]"
        return safe

    def to_headers(self) -> Dict[str, str]:
        """Headers HTTP para tracing."""
        return {
            "X-Request-ID": self.request_id,
            "X-Session-ID": hash_session_id(self.session_id),
        }
