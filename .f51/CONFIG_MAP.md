# F51 Config Map — SuperEzio
Generated: 2026-05-15

## Config Files

| File | Format | Description |
|---|---|---|
| `config/mandamentos.json` | JSON | Regras/mandamentos do sistema (carregado por `load_mandamentos()`) |
| `config/runtime.yml` | YAML | Config de runtime |
| `config/model_manifest.json` | JSON | Manifesto de modelos disponiveis |

## Config Schema

| Class | File | Fields |
|---|---|---|
| `UniversalConfig` | `src/core/config/schema.py` | `project_name`, `version`, `server`, `memory`, `storage`, `observability`, `triade`, `event_hub` |
| `ModelConfig` | `src/core/config/schema.py` | Model config para providers |
| `GatewayConfig` | `src/core/config/schema.py` | Config do ModelGateway |
| `EventHubConfig` | `src/core/config/schema.py` | Tipo de event hub (memory/redis) |
| `StorageConfig` | `src/core/config/schema.py` | Diretorios de storage |
| `MemoryConfig` | `src/core/config/schema.py` | Mem0 config (api_url, api_key, collection) |
| `ObservabilityConfig` | `src/core/config/schema.py` | OTEL flags |
| `ServerConfig` | `src/core/config/schema.py` | Host, port |
| `TriadeConfig` | `src/core/config/schema.py` | Config triade |

## Environment Variables (55 unique)

### Pipeline
| Var | Default | File |
|-----|---------|------|
| `SUPEREZIO_ORCHESTRATOR_TIMEOUT` | `12` | `pipeline/runtime.py` |
| `SUPEREZIO_CEO_TIMEOUT` | `120` | `pipeline/runtime.py` |
| `SUPEREZIO_DATA_TIMEOUT` | `60` | `pipeline/runtime.py` |
| `SUPEREZIO_EXPERT_TIMEOUT` | `60` | `pipeline/runtime.py` |
| `SUPEREZIO_EXPERT_CONCURRENCY` | `4` | `pipeline/runtime.py` |
| `SUPEREZIO_INTENT_LLM_FALLBACK` | `auto` | `pipeline/runtime.py` |
| `SUPEREZIO_INTENT_LLM_THRESHOLD` | `0.76` | `pipeline/runtime.py` |
| `SUPEREZIO_INTENT_LLM_TIMEOUT` | `4` | `pipeline/runtime.py` |
| `SUPEREZIO_SCAN_LIMIT` | `30` | `pipeline/runtime.py` |
| `UNIVERSAL_SKIP_GATEWAY` | (none) | `pipeline/runtime.py` |
| `SUPEREZIO_FORCE_ALL_EXPERTS_ON_PARTIAL` | `1` | `pipeline/nodes/_mixin.py` |
| `SUPEREZIO_PROFESSIONAL_COLLECTOR` | `true` | `pipeline/nodes/_mixin.py` |
| `SUPEREZIO_CEO_TEMPERATURE` | `0.2`-`0.4` | `pipeline/nodes/` |
| `SUPEREZIO_CEO_MAX_TOKENS` | `4096`-`8192` | `pipeline/nodes/` |

### Model Serving
| Var | Default | File |
|-----|---------|------|
| `SUPEREZIO_PRIMARY_API_KEY` | (none) | `agent_server/main.py` |
| `SUPEREZIO_DEEPSEEK_API_KEY` | (none) | `agent_server/main.py` |
| `SUPEREZIO_DEEPSEEK_MODEL` | `deepseek-chat` | `agent_server/main.py` |
| `SUPEREZIO_DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | `agent_server/main.py` |
| `SUPEREZIO_DEEPSEEK_TIMEOUT_SEC` | `120` | `model_serving/deepseek_provider.py` |
| `SUPEREZIO_DEEPSEEK_MAX_TOKENS` | `1800`-`4096` | `model_serving/` |
| `SUPEREZIO_DEEPSEEK_TEMPERATURE` | `0.2` | `model_serving/deepseek_provider.py` |
| `SUPEREZIO_DEEPSEEK_REASONING_EFFORT` | `high` | `model_serving/` |
| `SUPEREZIO_DEEPSEEK_THINKING` | `disabled` | `model_serving/gateway.py` |

### Data Providers
| Var | Default | File |
|-----|---------|------|
| `WOLFRAM_API_KEY` | (none) | `data/wolfram_provider.py` |
| `TWELVE_DATA_API_KEY` | (none) | `data/twelve_data.py` |
| `ALPHA_VANTAGE_API_KEY` | (none) | `data/alpha_vantage.py` |
| `BRAVE_SEARCH_API_KEY` | (none) | `data/news_feed.py` |
| `NEWSAPI_KEY` | (none) | `data/news_feed.py` |
| `SUPEREZIO_REDDIT_ENABLED` | `1` | `data/reddit_provider.py` |
| `SUPEREZIO_REDDIT_SUBREDDITS` | (none) | `data/reddit_provider.py` |
| `SUPEREZIO_TAVILY_SEARCH_PATH` | `""` | `data/data_hub.py` |
| `SUPEREZIO_TAVILY_EXTRACT_PATH` | `""` | `data/data_hub.py` |

### Infrastructure
| Var | Default | File |
|-----|---------|------|
| `A2A_PORT` | `8002` | `agent_server/main.py` |
| `A2A_BIND` | `127.0.0.1` | `agent_server/main.py` |
| `A2A_AGENT_NAME` | `generic_agent` | `agent_server/main.py` |
| `MEM0_API_URL` | (config) | `config/schema.py` |
| `MEM0_API_KEY` | (config) | `config/schema.py` |
| `MEM0_REDIS_URL` | `""` | `agent_server/main.py` |
| `CORS_ORIGINS` | (none) | `config/schema.py` |
| `SUPEREZIO_HOST` | (config) | `config/schema.py` |
| `SUPEREZIO_PORT` | (config) | `config/schema.py` |

### Observability & RAG
| Var | Default | File |
|-----|---------|------|
| `SUPEREZIO_DEBUG` | `""` | `observability/debug_logger.py` |
| `DISABLE_OTEL` | (none) | `observability/neural_log.py` |
| `SUPEREZIO_RAG_MODEL` | `all-MiniLM-L6-v2` | `rag/engine.py` |
| `SUPEREZIO_RAG_TOP_K` | `5` | `rag/engine.py` |
| `SUPEREZIO_RAG_CONTEXT_MAX_CHARS` | `2500` | `rag/engine.py` |
| `SUPEREZIO_RAG_DISABLED` | `0` | `rag/engine.py` |
| `SUPEREZIO_CACHE_DIR` | `""` | `data_collector/professional.py` |
| `SUPEREZIO_DATA_DIR` | `data` | `investor/storage.py` |

### PennyLab
| Var | Default | File |
|-----|---------|------|
| `PENNYLAB_JOURNAL` | `(auto)` | `experts/pennylab/config.py` |
| `PENNYLAB_MAX_USD` | `50.0` | `experts/pennylab/config.py` |
| `PENNYLAB_MAX_PRICE` | `5.0` | `experts/pennylab/config.py` |
| `PENNYLAB_MIN_VOLUME` | `500000` | `experts/pennylab/config.py` |

### Misc
| Var | Default | File |
|-----|---------|------|
| `SUPEREZIO_ENABLE_PYTHON_EXEC` | `""` | `tools/custom_tools.py` |
| `EXPLANATION_MODEL_PATH` | `""` | `explanation/engine.py` |
| `EXPLANATION_LORA_PATH` | (none) | `explanation/engine.py` |
