"""
Teste de integridade e auditoria do dataset canônico de enforcement.
Garante que data/fraud_patterns/enforcement_cases.jsonl não contenha
placeholders, URLs quebradas ou dados de mentira, e que o manifesto esteja íntegro.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_FILE = PROJECT_ROOT / "data" / "fraud_patterns" / "enforcement_cases.jsonl"
MANIFEST_FILE = PROJECT_ROOT / "data" / "fraud_patterns" / "enforcement_cases.MANIFEST.json"


def test_enforcement_cases_file_exists_and_not_empty():
    assert CASES_FILE.exists(), "Arquivo de casos de enforcement deve existir"
    assert CASES_FILE.stat().st_size > 5000, "Arquivo deve conter dados substanciais"


def test_manifest_matches_enforcement_dataset():
    assert MANIFEST_FILE.exists(), "Manifesto deve existir"
    with MANIFEST_FILE.open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    raw_data = CASES_FILE.read_bytes()
    expected_sha256 = hashlib.sha256(raw_data).hexdigest()
    assert manifest["sha256"] == expected_sha256, "SHA256 do arquivo deve coincidir com o manifesto"

    lines = [json.loads(line) for line in raw_data.decode("utf-8").splitlines() if line.strip()]
    assert len(lines) == manifest["total_cases"], "Contagem de casos deve coincidir com o manifesto"
    assert len(lines) >= 80, "Deve haver ao menos 80 casos reais catalogados"


def test_zero_placeholders_and_valid_canonical_urls():
    with CASES_FILE.open("r", encoding="utf-8") as fh:
        cases = [json.loads(line) for line in fh if line.strip()]

    for case in cases:
        url = case.get("source_url", "")
        case_id = case.get("case_id", "")
        assert url.startswith("http"), f"URL deve ser válida para o caso {case_id}"
        assert "xxx" not in url.lower(), (
            f"Proibido placeholder 'xxx' na URL do caso {case_id}: {url}"
        )
        assert case.get("date"), f"Data não pode ser nula no caso {case_id}"
        assert case.get("summary"), f"Resumo não pode ser vazio no caso {case_id}"
        assert case.get("case_type"), f"case_type obrigatório no caso {case_id}"
        assert case.get("market") in {"US", "CA"}, f"Mercado deve ser US ou CA no caso {case_id}"
