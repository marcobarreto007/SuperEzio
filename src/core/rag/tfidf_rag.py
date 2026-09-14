"""TF-IDF retrieval over curated knowledge — lexical ranking without embeddings.

Motivação medida: a busca por substring do `fraud_rag` ordena por
`len(texto)` (não por relevância), então qualquer query devolve os mesmos
três documentos mais longos e o índice não discrimina. Sobre um corpus de
500+ documentos curados o problema piora: termos ubíquos ("analysis",
"asset") casam com 80%+ do corpus.

TF-IDF resolve sem dependência nova (scikit-learn já é dependência do
projeto): o IDF faz um termo raro ("pump", "insider") pesar mais que um
termo onipresente, e o cosseno dá um score calibrado entre 0 e 1.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MIN_SCORE = 0.05


def corpus_digest(docs: list[dict[str, Any]]) -> tuple[int, str]:
    """Assinatura barata do corpus (tamanho + hash de ids/textos).

    Permite pular o refit do TF-IDF quando nada mudou — o `engine` recarrega
    os documentos do disco a cada busca, então a lista é sempre um objeto
    novo e comparação por identidade não serviria.
    """
    digest = hashlib.blake2b(digest_size=8)
    for doc in docs:
        digest.update(str(doc.get("id") or "").encode("utf-8", "replace"))
        digest.update(b"\x00")
        digest.update(str(doc.get("text") or "").encode("utf-8", "replace"))
        digest.update(b"\x00")
    return len(docs), digest.hexdigest()


class TfidfRetriever:
    """IDF-weighted lexical retriever over a list of {id, text, source} documents.

    Uso:
        r = TfidfRetriever()
        if r.fit(docs):
            hits = r.search("pump and dump", top_k=3)

    `fit` é idempotente: refaz o índice só quando o conteúdo do corpus muda.
    Nunca levanta por corpus vazio, query vazia ou scikit-learn ausente —
    devolve lista vazia e quem chama decide o fallback.
    """

    def __init__(
        self,
        ngram_range: tuple[int, int] = (1, 2),
        sublinear_tf: bool = True,
        min_score: float = DEFAULT_MIN_SCORE,
    ):
        self.ngram_range = ngram_range
        self.sublinear_tf = sublinear_tf
        self.min_score = min_score
        self._vectorizer: Any = None
        self._matrix: Any = None
        self._docs: list[dict[str, Any]] = []
        self._digest: tuple[int, str] | None = None

    @property
    def ready(self) -> bool:
        """True quando há índice construído."""
        return self._vectorizer is not None and self._matrix is not None

    def fit(self, docs: list[dict[str, Any]]) -> bool:
        """(Re)constrói o índice. Retorna False quando não há o que indexar."""
        prepared = [d for d in docs if str(d.get("text") or "").strip()]
        digest = corpus_digest(prepared)
        if self.ready and digest == self._digest:
            return True

        self._docs = prepared
        self._vectorizer = None
        self._matrix = None
        self._digest = None
        if not prepared:
            return False

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            self._vectorizer = TfidfVectorizer(
                ngram_range=self.ngram_range,
                sublinear_tf=self.sublinear_tf,
                lowercase=True,
            )
            self._matrix = self._vectorizer.fit_transform([str(d["text"]) for d in prepared])
        # Fronteira de melhor esforco: vocabulario vazio (corpus so com
        # pontuacao) desativa o indice em vez de derrubar a busca.
        except (ImportError, ValueError) as exc:
            logger.warning("TfidfRetriever: fit falhou (%s) — índice inerte", exc)
            self._vectorizer = None
            self._matrix = None
            return False

        self._digest = digest
        return True

    def search(
        self, query: str, top_k: int = 5, min_score: float | None = None
    ) -> list[dict[str, Any]]:
        """Top-k documentos por similaridade de cosseno contra a query.

        Retorna dicts {id, text, source, score}. Lista vazia quando a query
        não tem termo no vocabulário (ex.: um ticker que não aparece no corpus).
        """
        if not self.ready or not str(query or "").strip():
            return []

        threshold = self.min_score if min_score is None else min_score
        try:
            from sklearn.metrics.pairwise import cosine_similarity

            scores = cosine_similarity(self._vectorizer.transform([query]), self._matrix)[0]
        # Fronteira de melhor esforco: query so com stopwords vira vetor nulo;
        # sem resultado e melhor que excecao na busca.
        except (ValueError, ImportError) as exc:
            logger.debug("TfidfRetriever: query ignorada (%s)", exc)
            return []

        results: list[dict[str, Any]] = []
        for i in scores.argsort()[::-1]:
            score = float(scores[i])
            if score <= threshold:
                break  # argsort decrescente: daqui pra baixo nao melhora
            doc = self._docs[int(i)]
            results.append({**doc, "score": round(score, 4)})
            if len(results) >= top_k:
                break
        return results
