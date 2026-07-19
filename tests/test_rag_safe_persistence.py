import json

import src.core.rag.engine as engine_module
from src.core.rag.engine import ForensicRAG


def test_rag_persistence_uses_json_manifest_without_pickle(tmp_path, monkeypatch):
    documents = [
        {"id": "doc-1", "text": "verified evidence", "source": "test"},
        {"id": "doc-2", "text": "second fact", "source": "test"},
    ]
    monkeypatch.setattr(engine_module, "_documents_cache", documents.copy())
    monkeypatch.setattr(engine_module, "_faiss_index", None)
    rag = ForensicRAG()

    rag.save_index(str(tmp_path))
    current = (tmp_path / "CURRENT").read_text(encoding="utf-8").strip()
    generation = tmp_path / "generations" / current
    manifest = json.loads((generation / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["document_count"] == 2
    assert (generation / "documents.jsonl").exists()
    assert not (tmp_path / "documents.npy").exists()

    monkeypatch.setattr(engine_module, "_documents_cache", [])
    assert rag.load_index(str(tmp_path)) is True
    assert engine_module._documents_cache == documents


def test_rag_loader_rejects_tampered_documents(tmp_path, monkeypatch):
    monkeypatch.setattr(
        engine_module,
        "_documents_cache",
        [{"id": "doc-1", "text": "verified evidence", "source": "test"}],
    )
    monkeypatch.setattr(engine_module, "_faiss_index", None)
    rag = ForensicRAG()
    rag.save_index(str(tmp_path))
    current = (tmp_path / "CURRENT").read_text(encoding="utf-8").strip()
    documents_path = tmp_path / "generations" / current / "documents.jsonl"
    documents_path.write_text('{"id":"evil","text":"changed","source":"test"}\n')

    assert rag.load_index(str(tmp_path)) is False
