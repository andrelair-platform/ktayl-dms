.PHONY: install lint test run

install:
	pip install -e ".[test]"

lint:
	ruff check .
	ruff format --check .
	mypy app

test:
	pytest tests/unit -q

run:
	uvicorn app.main:app --reload --port 8000
