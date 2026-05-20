# Entrypoint Map - SuperEzio

> Atualizado: 2026-05-20T12:03:55-04:00 | Session: f51-inventory-codex-2026-05-20 | GitHub: DISK ONLY

## Primary Entrypoints
- `[app]` `desktop\\SuperEzio.bat` -> `desktop/SuperEzio.bat` - Windows launcher. Risk: loads .env and manages ports/browser
- `[app]` `open frontend/index.html after API is running` -> `frontend/index.html` - static frontend. Risk: expects API endpoints on localhost
- `[app]` `powershell -ExecutionPolicy Bypass -File scripts/serve_ceo_llamacpp.ps1` -> `scripts/serve_ceo_llamacpp.ps1` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[app]` `powershell -ExecutionPolicy Bypass -File scripts/serve_ceo_llamacpp.ps1 -Port 8082` -> `scripts/serve_ceo_llamacpp.ps1` - local llama.cpp CEO server. Risk: depends on local GGUF/model path and llama.cpp binary
- `[app]` `python -m agent_server.main` -> `src/agent_server/main.py` - FastAPI API server. Risk: requires PYTHONPATH=src or installed package; runtime.yml sets port 8002
- `[app]` `python -m experts.pennylab.cli` -> `src/experts/pennylab/cli.py` - PennyLab CLI. Risk: depends on provider/data availability
- `[experimental]` `scripts/cloud_merge_and_quantize.sh` -> `scripts/cloud_merge_and_quantize.sh` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[experimental]` `scripts/cloud_nextn_pipeline.sh` -> `scripts/cloud_nextn_pipeline.sh` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[experimental]` `scripts/cloud_rebuild_pipeline.sh` -> `scripts/cloud_rebuild_pipeline.sh` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[experimental]` `scripts/convert_gguf.sh` -> `scripts/convert_gguf.sh` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[experimental]` `python scripts/finetune_gemma_sft.py` -> `scripts/finetune_gemma_sft.py` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[experimental]` `python scripts/finetune_glm_sft.py` -> `scripts/finetune_glm_sft.py` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[experimental]` `python scripts/finetune_qwen36_sft.py` -> `scripts/finetune_qwen36_sft.py` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[experimental]` `scripts/merge_pipeline_h200.sh` -> `scripts/merge_pipeline_h200.sh` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[experimental]` `python scripts/merge_qwen36_lora.py` -> `scripts/merge_qwen36_lora.py` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[experimental]` `python scripts/run_merge_patched.py` -> `scripts/run_merge_patched.py` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[experimental]` `python scripts/sftp_download_chunks.py` -> `scripts/sftp_download_chunks.py` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[experimental]` `python scripts/train_qwen36_3h.py` -> `scripts/train_qwen36_3h.py` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[experimental]` `scripts/vastai_onstart.sh` -> `scripts/vastai_onstart.sh` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[experimental]` `scripts/vastai_setup_gemma.sh` -> `scripts/vastai_setup_gemma.sh` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[experimental]` `scripts/vastai_setup_intent.sh` -> `scripts/vastai_setup_intent.sh` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[experimental]` `scripts/vastai_setup_qwen36.sh` -> `scripts/vastai_setup_qwen36.sh` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[pipeline]` `python scripts/build_hf_intent_dataset.py` -> `scripts/build_hf_intent_dataset.py` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[pipeline]` `python scripts/generate_intent_dataset.py` -> `scripts/generate_intent_dataset.py` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[pipeline]` `python scripts/generate_system_knowledge_sft.py` -> `scripts/generate_system_knowledge_sft.py` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[test]` `python scripts/eval_pipeline.py` -> `scripts/eval_pipeline.py` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[test]` `python scripts/investment_test.py` -> `scripts/investment_test.py` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services
- `[test]` `python scripts/trick_questions_test.py` -> `scripts/trick_questions_test.py` - script entrypoint candidate. Risk: inspect arguments before running; may require secrets, GPU, cloud, or live services

## API Routes
- `[app]` `src/agent_server/main.py:186` @app.get("/")
- `[app]` `src/agent_server/main.py:199` @app.get("/favicon.ico", include_in_schema=False)
- `[app]` `src/agent_server/main.py:212` @app.api_route("/health", methods=["GET", "HEAD"])
- `[app]` `src/agent_server/main.py:224` @app.get("/health/details")
- `[app]` `src/agent_server/main.py:370` @app.get("/metrics")
- `[app]` `src/agent_server/main.py:381` @app.get("/neural/logs")
- `[app]` `src/agent_server/endpoints.py:96` @router.get("/api/chart-data/{ticker}")
- `[app]` `src/agent_server/endpoints.py:175` @router.get("/api/chart-sse/{ticker}")
- `[app]` `src/agent_server/endpoints.py:485` @router.post("/task/submit")
- `[app]` `src/agent_server/endpoints.py:611` @router.get("/capabilities")
- `[app]` `src/agent_server/endpoints.py:629` @router.get("/product/manifest")
- `[app]` `src/agent_server/endpoints.py:642` @router.post("/api/sdca/evaluate")
- `[app]` `src/agent_server/endpoints.py:650` @router.post("/experts/neural-decision/predict")

## Runtime Order From config/runtime.yml
- `[app]` CEO: `powershell -ExecutionPolicy Bypass -File scripts/serve_ceo_llamacpp.ps1 -Port 8082`.
- `[app]` API: `python -m agent_server.main` on `127.0.0.1:8002`.
- `[app]` Frontend: `frontend/index.html` calls API routes such as `/health`, `/api/chart-data/{ticker}`, `/task/submit`, `/api/sdca/evaluate`.
