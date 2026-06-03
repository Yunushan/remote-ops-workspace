.PHONY: install test verify verify-quick lint compile run-web

install:
	python -m pip install -e ".[desktop,security,dev]"

test:
	python scripts/verify.py

verify:
	python scripts/verify.py

verify-quick:
	python scripts/verify.py --quick

compile:
	python -m compileall src tests scripts

lint:
	python scripts/verify.py --quick --lint --no-cli-smoke

run-web:
	row serve-web --host 127.0.0.1 --port 8765
