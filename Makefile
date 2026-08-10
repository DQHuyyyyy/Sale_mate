.PHONY: help install install-api install-fe run-ai run-api fe test test-api cov \
        lint format typecheck check check-all infra infra-down clean sync-deploy \
        data-status data-ingest data-eval

# Windows dùng .venv/Scripts, Linux/macOS dùng .venv/bin
PY := .venv/bin/python
ifeq ($(OS),Windows_NT)
	PY := .venv/Scripts/python.exe
endif

# .venv tạo bằng uv thì bên trong KHÔNG có pip — `python -m pip` sẽ báo
# "No module named pip". Dùng uv khi có, không thì rơi về pip.
# Cách dò phải khác nhau theo hệ: trên Windows `make` chạy recipe bằng cmd.exe
# khi không tìm thấy sh.exe, mà cmd không hiểu `command -v` lẫn `/dev/null`.
ifeq ($(OS),Windows_NT)
	UV_PATH := $(shell where uv 2>NUL)
else
	UV_PATH := $(shell command -v uv 2>/dev/null)
endif

PIP_INSTALL := $(PY) -m pip install
ifneq (,$(UV_PATH))
	PIP_INSTALL := uv pip install --python $(PY)
endif

help:
	@echo "--- Cai dat ---"
	@echo "install      Dependencies cho loi AI (src/)"
	@echo "install-api  Dependencies cho API san pham (interface/backend/)"
	@echo "install-fe   Dependencies frontend"
	@echo "--- Chay ---"
	@echo "run-api      API san pham  -> http://localhost:8000/docs"
	@echo "run-ai       Loi AI + RAG  -> http://localhost:8001/docs"
	@echo "fe           Frontend      -> http://localhost:5173"
	@echo "infra        Bat Qdrant + Postgres bang Docker"
	@echo "--- Du lieu RAG ---"
	@echo "data-status  Vector store dang co gi"
	@echo "data-ingest  Nap toan bo 4 nguon vao Qdrant"
	@echo "data-eval    Do truy hoi tren bo cau hoi vang"
	@echo "--- Kiem tra ---"
	@echo "test         Test loi AI (tests/)"
	@echo "test-api     Test API san pham (interface/backend/tests/)"
	@echo "check        lint + format + test cho src/  (chay truoc khi push)"
	@echo "check-all    check + test-api"
	@echo "--- Deploy ---"
	@echo "sync-deploy  Day main + develop tu repo BTC sang mirror ca nhan"

# ---------- Cài đặt ----------

install:
	$(PIP_INSTALL) -r requirements.txt -r requirements-dev.txt

install-api:
	$(PIP_INSTALL) -r interface/backend/requirements.txt -r interface/backend/requirements-dev.txt

install-fe:
	cd interface/frontend && npm install

# ---------- Chạy ----------

# API sản phẩm: auth, apartments, zones, sales, documents, chat.
# Frontend proxy /api thẳng vào cổng này.
run-api:
	cd interface/backend && ../../$(PY) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Lõi AI: agent graph + RAG. interface/backend/ gọi vào đây qua AI_CORE_URL.
run-ai:
	$(PY) -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8001

fe:
	cd interface/frontend && npm run dev

infra:
	docker compose up -d qdrant db

infra-down:
	docker compose down

# ---------- Kiểm tra ----------

test:
	$(PY) -m pytest tests/

test-api:
	cd interface/backend && ../../$(PY) -m pytest tests/

cov:
	$(PY) -m pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=60

lint:
	$(PY) -m ruff check src/ tests/

format:
	$(PY) -m ruff format src/ tests/

typecheck:
	$(PY) -m mypy src/

check: lint format test

check-all: check test-api

# ---------- Du lieu RAG ----------
# Moi thao tac di qua src/cli.py — cung cau hinh voi ung dung, khong
# con moi nguon mot script tu dung pipeline rieng nhu truoc.

data-status:
	$(PY) -m src.cli status

data-ingest:
	$(PY) -m src.cli ingest --all

data-eval:
	$(PY) -m src.cli eval retrieval

# ---------- Deploy ----------

# Đẩy main + develop từ repo BTC sang mirror cá nhân để Render deploy.
#
# Logic nằm trong scripts/sync_deploy.py, không viết thẳng vào recipe: `make`
# trên Windows chạy recipe bằng cmd.exe khi không tìm thấy sh.exe, nên mọi cú
# pháp POSIX (for/do/done, {}, /dev/null) đều vỡ khi gọi từ PowerShell.
DEPLOY_REMOTE := deploy

sync-deploy:
	$(PY) scripts/sync_deploy.py $(DEPLOY_REMOTE)

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
