.PHONY: install test lint compile run-web

install:
	python -m pip install -e ".[desktop,security,dev]"

test:
	pytest -q

compile:
	python -m compileall src

lint:
	ruff check src tests

run-web:
	row serve-web --host 127.0.0.1 --port 8765
