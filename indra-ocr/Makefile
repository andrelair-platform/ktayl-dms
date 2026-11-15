.PHONY: install lint test test-smoke run

install:
	pip install -e ".[test]"

lint:
	ruff check .
	ruff format --check .
	mypy .

test:              ## L1 unit (indra mocked, fast, no model)
	pytest tests/unit -q

test-smoke:        ## real indra (downloads the model, slow)
	pytest tests/smoke -q

run:
	uvicorn app.main:app --reload --port 8000
