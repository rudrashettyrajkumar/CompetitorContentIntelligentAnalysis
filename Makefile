VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: install test lint fmt run demo clean

install:
	@test -d $(VENV) || python3 -m venv $(VENV)
	$(PIP) install --upgrade pip -q
	$(PIP) install -e ".[dev]" -q
	@echo "Installed. Activate with: source $(VENV)/bin/activate"

test:
	LLM_FAKE_MODE=true $(VENV)/bin/pytest -q

lint:
	$(VENV)/bin/ruff check src tests
	$(VENV)/bin/ruff format --check src tests

fmt:
	$(VENV)/bin/ruff check --fix src tests
	$(VENV)/bin/ruff format src tests

run:
	$(VENV)/bin/uvicorn app.api.main:app --reload --port 8000

demo:
	LLM_FAKE_MODE=true $(PY) -m app.demo

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
