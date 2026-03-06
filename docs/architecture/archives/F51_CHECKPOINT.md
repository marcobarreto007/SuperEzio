# F51 Checkpoint

**Data**: 2026-05-14
**Sessao**: Cleanup final + Nemotron-Nano-12B canonico — preparacao para entrega
**Status**: Codigo pronto para entrega com CEO Nemotron-Nano-12B merged (Phase 0 + Phase 1 QLoRA)

## Concluido nesta rodada

- CEO CANONICO: Nemotron-Nano-12B-v2 (6.83B params, Hybrid Mamba/MoE) servido via `scripts/serve_ceo.py` com HuggingFace Transformers CUDA.
- MERGE: Phase 0 (fraud/phishing LoRA, Vast.ai 3h) + Phase 1 (numerical SFT LoRA, local) merged via `merge_adapters.py` em `.f51/tmp/superezio-merged/` (8.3 GB).
- CLEANUP: 6 scripts mortos deletados (serve_ceo_llamacpp.ps1, download_ceo_model.py, launch_superezio_ceo.ps1, serve_ceo_nemotron.ps1, serve_ceo_nemotron.py, download_glm_gguf.py).
- CLEANUP: 4 providers mortos removidos (Grok, Gemini, CEO_LORA aliases, BOB aliases).
- CLEANUP: diretorio `scripts/legacy/` deletado.
- CLEANUP: scripts soltos deletados (build_f51_corpus.py, generate_sensei_responses.py, anthropic_glm_proxy.py, start_glm_proxy.bat, setup_claude_mcp.ps1).
- FIX: HttpProbe migrado de urllib para requests (urllib quebrava em Windows com ProxyHandler).
- FIX: serve_ceo.py — geracao nao-streaming usa `asyncio.to_thread()` para nao bloquear event loop.
- FIX: sanitizer regex `_PRIVATE_CHANNEL_RE` corrigido (nao engole mais o proximo marker).
- FIX: `_parse_model_tool_calls` agora stripa canais DEPOIS de extrair tool calls.
- DOC: CLAUDE.md, decision-tree.txt, checkpoints, README atualizados com referencias Nemotron.
- DOC: `serve_ceo.py` docstring documenta arquitetura completa (base, Phase 0, Phase 1, merge).

## Verificacoes

- `python -m pytest tests/ -q`: 496 passed, 0 failed, 2 warnings.
- `python -m ruff check src tests`: passed.
- `python -c "from f51 import F51Engine; ..."`: import e contrato OK.
- `python -c "from agent_server.main import app; ..."`: OK.
- CEO merged model: `.f51/tmp/superezio-merged/` (8.3 GB) verificado com todos os arquivos necessarios.
- Adaptadores fonte: `nemotron-adapter/` (104 MB) + `phase1-adapter/` (104 MB) — ambos baixados e merged.

## Riscos remanescentes

- Chaves antigas no historico do git — rotacionar antes de entrega publica.
- CEO local requer GPU CUDA >= 10 GB VRAM.
- Fase 2 (financial SFT 3h Vast.ai) nao existe separadamente — o `nemotron-adapter` JA E a fase 2.

## Proximo passo

Empacotamento final: requirements lock, script de setup, validacao de ambiente, documentacao de entrega ao cliente.
