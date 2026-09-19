"""Regressão: o RAG tem que DISCRIMINAR, não devolver o mesmo para qualquer query.

Contexto medido (2026-09-14): `FraudPatternMatcher.search_patterns` computava
um `score` e o descartava, ordenando por `len(texto)`. Resultado: três queries
sem relação ("pump and dump scheme", "insider trading", "SEC enforcement")
devolviam exatamente os mesmos três documentos — os mais longos do corpus.

Estes testes travam a correção e cobrem os três consumidores reais do
singleton: guardrail_hub, crisis_expert e pennylab/rag_hooks.
"""

import pytest

from core.rag.fraud_rag import FraudPatternMatcher, fraud_patterns
from core.rag.tfidf_rag import TfidfRetriever, corpus_digest


def _matcher_with(docs: list[str]) -> FraudPatternMatcher:
    """Matcher sem tocar o disco — injeta o corpus direto."""
    matcher = FraudPatternMatcher.__new__(FraudPatternMatcher)
    matcher.data_dir = ""
    matcher.knowledge_base = list(docs)
    matcher.pump_symbols = set()
    return matcher


# ── Correção do ranking por comprimento ────────────────────────────────


def test_ranking_prioriza_relevancia_nao_comprimento():
    """Um doc curto e relevante tem que vencer um doc longo e irrelevante.

    Este é o bug exato: antes, `len(texto)` decidia e o doc longo vencia.
    """
    matcher = _matcher_with(
        [
            "fraud fraud fraud fraud — caso curto e cem por cento relevante",
            "X" * 5000 + " uma menção solta de fraud lá no fim de um texto gigante",
        ]
    )

    top = matcher.search_patterns("fraud", limit=1)

    assert len(top) == 1
    assert "caso curto" in top[0]
    assert not top[0].startswith("[PATTERN_FOUND]: X")


def test_queries_diferentes_devolvem_resultados_diferentes():
    """Regressão direta: queries distintas não podem devolver o mesmo conjunto."""
    matcher = _matcher_with(
        [
            "pump and dump scheme: promoters inflate microcap prices then dump",
            "insider trading before announcement: executives trade on material info",
            "accounting fraud: revenue recognized before it was earned, restatement",
            "generic filler text about markets and long term investing discipline",
        ]
    )

    pump = matcher.search_patterns("pump and dump", limit=1)
    insider = matcher.search_patterns("insider trading", limit=1)
    accounting = matcher.search_patterns("accounting fraud", limit=1)

    assert pump != insider
    assert insider != accounting
    assert "pump" in pump[0]
    assert "insider" in insider[0]
    assert "accounting" in accounting[0]


def test_mais_keywords_casando_rankeia_acima():
    """Score é nº de keywords que casam — mais casamento vem primeiro."""
    matcher = _matcher_with(
        [
            "documento que menciona apenas fraud",
            "documento que menciona fraud e manipulação e pump",
        ]
    )

    top = matcher.search_patterns("fraud manipulation pump", limit=1)

    assert "e manipulação e pump" in top[0]


def test_mesmo_score_desempata_pelo_texto_mais_curto():
    matcher = _matcher_with(
        [
            "fraud " + "preenchimento irrelevante " * 40,
            "fraud curto",
        ]
    )

    top = matcher.search_patterns("fraud", limit=1)

    assert top[0].endswith("fraud curto...")


def test_pump_symbol_alerta_vem_primeiro():
    matcher = _matcher_with(["fraud fraud fraud em texto muito curto"])
    matcher.pump_symbols = {"PUMP"}

    top = matcher.search_patterns("PUMP", limit=1)

    assert top[0].startswith("[TECHNICAL_ALERT]")


def test_query_vazia_ou_curta_nao_quebra():
    """Query vazia, só espaços e palavras de <=3 chars seguem devolvendo lista."""
    matcher = _matcher_with(["um documento qualquer sobre fraudes"])

    assert matcher.search_patterns("") == []
    assert matcher.search_patterns("   ") == []
    assert matcher.search_patterns("a") == []
    assert matcher.search_patterns("SEC IPO CEO") == []
    assert isinstance(matcher.search_patterns("xyzzy nonsense"), list)


def test_limite_respeitado_com_corpus_grande():
    """Corpus saturado não pode estourar o limite pedido."""
    matcher = _matcher_with([f"valuation note {i}: analysis of macro" for i in range(500)])

    assert len(matcher.search_patterns("valuation analysis", limit=3)) == 3
    assert len(matcher.search_patterns("valuation analysis", limit=10)) == 10


# ── TfidfRetriever ─────────────────────────────────────────────────────


def _docs(n: int, filler: bool = False) -> list[dict]:
    docs = [{"id": "pump-doc", "text": "pump and dump: promoters inflate then dump", "source": "t"}]
    docs.append(
        {"id": "insider-doc", "text": "insider trading ahead of announcement", "source": "t"}
    )
    if filler:
        docs.extend(
            {
                "id": f"fill-{i}",
                "text": f"valuation note {i}: analysis of macro and earnings for asset class etf",
                "source": "t",
            }
            for i in range(500)
        )
    return docs


def test_tfidf_discrimina_com_500_documentos():
    """O ponto do exercício: 500+ docs curados e a busca ainda separa os assuntos."""
    retriever = TfidfRetriever()
    assert retriever.fit(_docs(500, filler=True))

    pump = retriever.search("pump and dump", top_k=1)
    insider = retriever.search("insider trading", top_k=1)

    assert pump and pump[0]["id"] == "pump-doc"
    assert insider and insider[0]["id"] == "insider-doc"


def test_tfidf_termo_raro_pesa_mais_que_termo_ubiquo():
    """IDF: "valuation" aparece em 500 docs, "pump" em 1 — o raro tem que ganhar."""
    retriever = TfidfRetriever()
    assert retriever.fit(_docs(500, filler=True))

    hits = retriever.search("valuation pump", top_k=1)

    assert hits[0]["id"] == "pump-doc"


def test_tfidf_query_fora_do_vocabulario_devolve_vazio():
    retriever = TfidfRetriever()
    assert retriever.fit(_docs(500, filler=True))

    assert retriever.search("xyzzy plugh") == []
    assert retriever.search("") == []
    assert retriever.search("   ") == []


def test_tfidf_corpus_vazio_e_inerte():
    retriever = TfidfRetriever()

    assert retriever.fit([]) is False
    assert retriever.ready is False
    assert retriever.search("qualquer coisa") == []


def test_tfidf_refit_pulado_quando_corpus_nao_muda():
    """A assinatura evita refit a cada busca (o engine recarrega do disco sempre)."""
    retriever = TfidfRetriever()
    docs = _docs(500, filler=True)

    assert retriever.fit(docs)
    matrix_before = retriever._matrix
    assert retriever.fit(list(docs)) is True
    assert retriever._matrix is matrix_before

    docs.append({"id": "novo", "text": "documento novo sobre pump", "source": "t"})
    assert retriever.fit(docs) is True
    assert retriever._matrix is not matrix_before


def test_corpus_digest_sensivel_a_id_e_texto():
    base = [{"id": "a", "text": "um"}]

    assert corpus_digest(base) == corpus_digest([dict(base[0])])
    assert corpus_digest(base) != corpus_digest([{"id": "b", "text": "um"}])
    assert corpus_digest(base) != corpus_digest([{"id": "a", "text": "dois"}])


# ── O engine usa o caminho ranqueado ───────────────────────────────────


def test_engine_search_sem_embedder_discrimina():
    """Sem sentence-transformers, `search` tem que ranquear, não só contar keywords."""
    from core.rag import engine as engine_module

    rag = engine_module.ForensicRAG(data_dir="data/nonexistent_dir_for_test")
    hits = rag.search("pump and dump scheme", top_k=3)

    assert isinstance(hits, list)
    if hits:
        # o caminho ranqueado devolve score calibrado em [0, 1]
        assert all(0.0 < h["score"] <= 1.0 for h in hits)
        assert all({"id", "text", "source"} <= set(h) for h in hits)


def test_engine_ranked_search_cai_no_keyword_se_tfidf_vazio():
    from core.rag import engine as engine_module

    rag = engine_module.ForensicRAG(data_dir="data/nonexistent_dir_for_test")
    fallback = [{"id": "kw", "text": "achado por keyword", "source": "kw", "score": 1.0}]

    original = engine_module.ForensicRAG._keyword_search
    engine_module.ForensicRAG._keyword_search = lambda self, q, top_k=5: fallback
    try:
        assert rag._ranked_search("xyzzy plugh", top_k=3) == fallback
    finally:
        engine_module.ForensicRAG._keyword_search = original


# ── Documentos de runtime sobrevivem ao reload do disco ───────────────


def test_add_document_sobrevive_a_busca_seguinte():
    """Regressão: `_ensure_index` recarrega do disco e apagava o doc de runtime.

    Era o motivo de a ingestão do unified.py (conversas e paper trades) nunca
    virar resultado: o documento sumia na busca imediatamente seguinte.
    """
    from core.rag import engine as engine_module

    rag = engine_module.ForensicRAG()
    rag.search("pump and dump", top_k=2)  # aquece o índice
    antes = len(engine_module._documents_cache)

    rag.add_document(
        "TRADE-REG-1",
        "paper trade thesis exclusiva sobre ticker zzzrev com pump and dump",
        source="paper_journal",
    )
    assert len(engine_module._documents_cache) == antes + 1

    rodou = rag.search("ticker zzzrev pump", top_k=5)

    assert "TRADE-REG-1" in [h["id"] for h in rodou]


def test_add_document_nao_desalinha_vetor_e_documento(monkeypatch):
    """Regressão: rebuild com docs de runtime desalinhava vetor e documento.

    `_ensure_index` montava o índice de vetores só com os docs de disco,
    enquanto `_documents_cache` recebia disco + runtime. O vetor anexado por
    `add_document` caía numa posição que o leitor resolvia para OUTRO
    documento: a busca devolvia o id/text de um registro diferente e o doc
    recém-ingerido não aparecia. Era a causa real de
    `test_add_document_sobrevive_a_busca_seguinte` falhar na suíte completa e
    passar isolado — qualquer teste anterior que ingerisse doc de runtime
    criava a pré-condição.

    O singleton é global e compartilhado pela sessão inteira, então o teste
    parte de estado zerado e o monkeypatch devolve os objetos originais no
    teardown: sem isso este teste viraria o próximo poluidor.
    """
    from core.rag import engine as engine_module

    monkeypatch.setattr(engine_module, "_documents_cache", [])
    monkeypatch.setattr(engine_module, "_runtime_docs", [])
    monkeypatch.setattr(engine_module, "_embeddings_cache", None)
    monkeypatch.setattr(engine_module, "_faiss_index", None)
    monkeypatch.setattr(engine_module, "_index_data_dir", None)

    rag = engine_module.ForensicRAG()
    # Um doc de runtime ANTES do primeiro rebuild é a pré-condição do defeito.
    rag.add_document("DECOY-RUNTIME", "documento de runtime anterior sobre pump and dump")
    rag.search("pump and dump", top_k=2)

    alvo = "thesis exclusiva sobre ticker qqqrev com pump and dump"
    rag.add_document("TRADE-REG-2", alvo)

    if engine_module._faiss_index is not None:
        # O leitor resolve índices de vetor através de _documents_cache.
        assert len(engine_module._documents_cache) == engine_module._faiss_index.ntotal

    hits = rag.search("ticker qqqrev pump", top_k=5)
    por_id = {h["id"]: h for h in hits}

    assert "TRADE-REG-2" in por_id
    # O id devolvido tem que carregar o PRÓPRIO texto, não o do decoy.
    assert por_id["TRADE-REG-2"]["text"] == alvo


def test_add_document_mesmo_id_nao_duplica_no_runtime():
    from core.rag import engine as engine_module

    rag = engine_module.ForensicRAG()
    rag.add_document("DUP-1", "primeira versao do documento sobre pump")
    rag.add_document("DUP-1", "segunda versao do documento sobre pump")

    registrados = [d for d in engine_module._runtime_docs if d["id"] == "DUP-1"]

    assert len(registrados) == 1
    assert registrados[0]["text"] == "segunda versao do documento sobre pump"


# ── Os três consumidores do singleton continuam funcionando ────────────


def test_consumidor_guardrail_hub():
    from core.pipeline.nodes.guardrail_hub import GuardrailHub

    hub = GuardrailHub.__new__(GuardrailHub)
    result = hub._fraud_rag({"ticker": "AAPL"})
    details = result["details"]

    assert isinstance(details["matches"], list)
    assert result["decision"] in {"ALLOW", "REVIEW"}
    assert result["decision"] == ("REVIEW" if details["matches"] else "ALLOW")


def test_consumidor_crisis_expert():
    from core.rag.fraud_rag import fraud_patterns as singleton
    from experts.crisis.expert.crisis_expert import CrisisMathExpert

    expert = CrisisMathExpert.__new__(CrisisMathExpert)
    expert._fraud_patterns = None
    expert._notifier = None

    assert expert._get_fraud_patterns() is singleton
    assert isinstance(singleton.search_patterns("AAPL"), list)


def test_consumidor_pennylab_rag_hooks():
    from experts.pennylab.rag_hooks import enrich_with_rag, query_fraud_patterns

    results = query_fraud_patterns("PUMP")

    assert isinstance(results, list)
    assert all(isinstance(r, str) for r in results)
    assert "test evidence" in enrich_with_rag("TEST", ["test evidence"])


def test_singleton_continua_instancia_do_matcher():
    """Contrato preservado: fraude_patterns é o FraudPatternMatcher canônico."""
    assert isinstance(fraud_patterns, FraudPatternMatcher)
    assert fraud_patterns.search_patterns("pump and dump", limit=3)


@pytest.mark.parametrize("limit", [0, 1, 3])
def test_limit_inclusive_zero_nao_quebra(limit):
    assert isinstance(fraud_patterns.search_patterns("pump and dump", limit=limit), list)
