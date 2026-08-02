.PHONY: help install run test cov lint format typecheck check infra infra-down fe fe-install clean

# Windows dùng .venv/Scripts, Linux/macOS dùng .venv/bin
PY := .venv/bin/python
ifeq ($(OS),Windows_NT)
	PY := .venv/Scripts/python.exe
endif

help:
	@echo "install     Cai dependencies backend (can .venv Python 3.11)"
	@echo "run         Chay backend  -> http://localhost:8000/docs"
	@echo "fe          Chay frontend -> http://localhost:3000"
	@echo "infra       Bat Qdrant + Postgres bang Docker"
	@echo "test        Chay test"
	@echo "cov         Chay test kem bao cao coverage"
	@echo "check       lint + format + test (chay truoc khi push)"

install:
	$(PY) -m pip install -r requirements.txt -r requirements-dev.txt

run:
	$(PY) -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	$(PY) -m pytest tests/

cov:
	$(PY) -m pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=60

lint:
	$(PY) -m ruff check src/ tests/

format:
	$(PY) -m ruff format src/ tests/

typecheck:
	$(PY) -m mypy src/

check: lint format test

infra:
	docker compose up -d qdrant db

infra-down:
	docker compose down

fe-install:
	cd frontend && npm install

fe:
	cd frontend && npm run dev

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
