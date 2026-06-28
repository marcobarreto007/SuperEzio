"""CI/CD smoke test — validates the system without starting servers."""
import sys
import os
import subprocess
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

def step(name):
    print(f"  [{name}]...", end=" ", flush=True)
    t0 = time.time()
    return t0

def ok(t0, extra=""):
    print(f"OK ({time.time()-t0:.1f}s) {extra}")

def fail(t0, msg):
    print(f"FAIL ({time.time()-t0:.1f}s) {msg}")
    return False

passed = 0
failed = 0

# 1. Settings
t0 = step("Settings")
try:
    from core.config.settings import get_settings
    s = get_settings()
    assert s.f51_trading_execution_freeze is not None
    ok(t0)
    passed += 1
except Exception as e:
    fail(t0, str(e)[:80]); failed += 1

# 2. F51 Trade Gate
t0 = step("F51 Gate")
try:
    from core.pipeline.f51_trade_gate import evaluate_trade_gate, is_execution_frozen
    gd = evaluate_trade_gate("comprar AAPL", "AAPL", qty=10, limit_price=150.0, run_id="ci")
    assert gd.status in ("ALLOW", "BLOCK")
    ok(t0, gd.reason_code)
    passed += 1
except Exception as e:
    fail(t0, str(e)[:80]); failed += 1

# 3. Historical cache
t0 = step("OHLCV Cache")
try:
    from core.trading.historical_cache import get_cache_stats
    cs = get_cache_stats()
    assert cs["tickers_cached"] > 0
    ok(t0, f"{cs['tickers_cached']} tickers")
    passed += 1
except Exception as e:
    fail(t0, str(e)[:80]); failed += 1

# 4. Expert cache
t0 = step("Expert Cache")
try:
    from core.trading.batch_expert_runner import get_expert_stats
    es = get_expert_stats()
    assert es["tickers_analyzed"] > 0
    ok(t0, f"{es['total_analyses']} analyses")
    passed += 1
except Exception as e:
    fail(t0, str(e)[:80]); failed += 1

# 5. Idempotency
t0 = step("Idempotency")
try:
    from core.idempotency import make_idempotency_key
    k1 = make_idempotency_key("AAPL", 10, 150.0)
    k2 = make_idempotency_key("AAPL", 10, 150.0)
    assert k1 == k2
    ok(t0)
    passed += 1
except Exception as e:
    fail(t0, str(e)[:80]); failed += 1

# 6. Pipeline graph compiles
t0 = step("Pipeline Graph")
try:
    from core.pipeline import build_graph
    ok(t0)
    passed += 1
except Exception as e:
    fail(t0, str(e)[:80]); failed += 1

# 7. Universe
t0 = step("Universe 391")
try:
    from core.trading.universe_builder import build_universe_400
    u = build_universe_400()
    assert len(u) > 300
    ok(t0, f"{len(u)} tickers")
    passed += 1
except Exception as e:
    fail(t0, str(e)[:80]); failed += 1

# 8. Fast cache hit
t0 = step("Cache Fast Path")
try:
    from core.pipeline.nodes.collector import _try_fast_cache
    events = []
    r = _try_fast_cache("NVDA", lambda e: events.append(e))
    assert r is not None
    assert r["_data_from_cache"]
    ok(t0, f"${r['data']['price']['latest']}")
    passed += 1
except Exception as e:
    fail(t0, str(e)[:80]); failed += 1

print(f"\n{'='*40}")
print(f"  PASSED: {passed}  FAILED: {failed}")
print(f"  STATUS: {'PASS' if failed == 0 else 'FAIL'}")
print(f"{'='*40}")
sys.exit(0 if failed == 0 else 1)
