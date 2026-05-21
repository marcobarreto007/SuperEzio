.PHONY: test test-windows install-deps verify

install-deps:
	pip install -r requirements.txt
	pip install pytest pytest-asyncio pytest-cov

test:
	python -m pytest tests/ -v --tb=short --maxfail=5

test-windows:
	@echo "Use scripts\run_tests.bat no Windows"

verify:
	python -m ruff check src tests
	python -m ruff format --check src tests
	python -m pytest tests -q
