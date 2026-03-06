"""
RAG Hooks — Integração com fraud_rag existente
===============================================
Reutiliza o fraud_rag do core sem duplicar lógica.
Se o provedor RAG não estiver disponível, retorna lista vazia
sem crashar o pipeline.

Princípio: RAG lembra. Python calcula. Marco decide.
"""

from __future__ import annotations

from typing import List


def query_fraud_patterns(ticker: str) -> List[str]:
    """
    Consulta o fraud_rag existente para padrões conhecidos de manipulação
    associados ao ticker ou ao setor.

    Retorna lista de strings de evidência para injetar no PennylabReport.
    Nunca lança exceção — degrada graciosamente.
    """
    try:
        from core.rag.fraud_rag import fraud_rag  # type: ignore[import]

        results = fraud_rag.search_patterns(ticker)
        if not results:
            return []
        # Normaliza para lista de strings
        evidence = []
        for r in results:
            if isinstance(r, str):
                evidence.append(f"[RAG/fraude] {r}")
            elif isinstance(r, dict):
                desc = r.get("description") or r.get("pattern") or str(r)
                evidence.append(f"[RAG/fraude] {desc}")
        return evidence
    except ImportError:
        return ["[RAG] fraud_rag indisponível neste ambiente"]
    except Exception as exc:  # noqa: BLE001
        return [f"[RAG] erro na consulta: {type(exc).__name__}"]


def enrich_with_rag(ticker: str, existing_evidence: List[str]) -> List[str]:
    """
    Adiciona evidências RAG à lista existente sem duplicar.
    Retorna nova lista combinada.
    """
    rag_evidence = query_fraud_patterns(ticker)
    # Evita duplicatas por comparação de texto
    combined = list(existing_evidence)
    for ev in rag_evidence:
        if ev not in combined:
            combined.append(ev)
    return combined
