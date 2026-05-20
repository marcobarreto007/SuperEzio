# Test Map - SuperEzio

> Atualizado: 2026-05-20T12:03:55-04:00 | Session: f51-inventory-codex-2026-05-20

## Recommended Commands
- `[test]` `python -m ruff check .`
- `[test]` `python -m ruff format --check .`
- `[test]` `python -m pytest`
- `[test]` `pyright . if installed`
- `[test]` `python -m pytest tests/contracts -q`
- `[test]` `python -m pytest tests/test_runtime_smoke.py -q`

## Test Files
- `[test]` `tests/conftest.py` - approx tests: 0; markers: pipeline, model_serving
- `[test]` `tests/contracts/__init__.py` - approx tests: 0; markers: unit/unknown
- `[test]` `tests/contracts/test_contract_a2a.py` - approx tests: 13; markers: contract, model_serving
- `[test]` `tests/contracts/test_contract_ceo.py` - approx tests: 31; markers: contract, pipeline, model_serving
- `[test]` `tests/contracts/test_contract_endpoints.py` - approx tests: 10; markers: runtime/api, contract, pipeline
- `[test]` `tests/contracts/test_contract_explanation.py` - approx tests: 9; markers: contract, model_serving
- `[test]` `tests/contracts/test_contract_f51_engine.py` - approx tests: 42; markers: contract
- `[test]` `tests/contracts/test_contract_main.py` - approx tests: 7; markers: runtime/api, contract, model_serving
- `[test]` `tests/contracts/test_contract_pipeline.py` - approx tests: 13; markers: contract, pipeline, model_serving
- `[test]` `tests/contracts/test_contract_rag.py` - approx tests: 9; markers: contract, model_serving
- `[test]` `tests/contracts/test_trading_losses.py` - approx tests: 25; markers: contract, pipeline, model_serving
- `[test]` `tests/helpers.py` - approx tests: 0; markers: pipeline, model_serving
- `[test]` `tests/test_components_crisis.py` - approx tests: 25; markers: contract, model_serving
- `[test]` `tests/test_components_data.py` - approx tests: 27; markers: model_serving
- `[test]` `tests/test_components_f51.py` - approx tests: 27; markers: unit/unknown
- `[test]` `tests/test_components_pennylab.py` - approx tests: 16; markers: unit/unknown
- `[test]` `tests/test_crisis.py` - approx tests: 51; markers: contract, model_serving
- `[test]` `tests/test_f51_engine.py` - approx tests: 15; markers: pipeline
- `[test]` `tests/test_f51_formulas.py` - approx tests: 26; markers: contract
- `[test]` `tests/test_gateway.py` - approx tests: 28; markers: pipeline, model_serving
- `[test]` `tests/test_integration_runtime.py` - approx tests: 7; markers: pipeline, model_serving
- `[test]` `tests/test_market_scanner.py` - approx tests: 3; markers: runtime/api, pipeline, model_serving
- `[test]` `tests/test_math.py` - approx tests: 37; markers: unit/unknown
- `[test]` `tests/test_model_sanitizer.py` - approx tests: 2; markers: model_serving
- `[test]` `tests/test_neural_decision.py` - approx tests: 20; markers: runtime/api, contract
- `[test]` `tests/test_pennylab.py` - approx tests: 56; markers: unit/unknown
- `[test]` `tests/test_pipeline_smoke.py` - approx tests: 8; markers: runtime/api, pipeline, model_serving
- `[test]` `tests/test_rag_engine_smoke.py` - approx tests: 0; markers: unit/unknown
- `[test]` `tests/test_runtime_smoke.py` - approx tests: 20; markers: runtime/api, pipeline, model_serving
- `[test]` `tests/test_sdca_lite.py` - approx tests: 14; markers: runtime/api, pipeline, model_serving
- `[test]` `tests/test_trading_loop1.py` - approx tests: 24; markers: unit/unknown
- `[test]` `tests/test_trading_loop2.py` - approx tests: 20; markers: unit/unknown
- `[test]` `tests/test_trading_loop3.py` - approx tests: 24; markers: unit/unknown
- `[test]` `tests/test_trading_loop4.py` - approx tests: 20; markers: unit/unknown
- `[test]` `tests/test_trading_loop5.py` - approx tests: 27; markers: pipeline, model_serving

## Coverage Gaps To Inspect Next
- `[unknown]` Inventory did not execute pytest; counts are static approximations from function names.
- `[core]` Prioritize import/contract validation for config, model serving, pipeline, and technical_neural expert package boundaries.
