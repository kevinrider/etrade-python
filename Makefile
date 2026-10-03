.PHONY: install venv-reset lint format format-check type test check build twine-check package-check clean

install:
	uv sync --extra dev

venv-reset:
	rm -rf .venv
	uv venv --python 3.12 .venv
	uv sync --extra dev

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

type:
	uv run pyright --pythonpath .venv/bin/python

test:
	uv run pytest

check: lint format-check type test

build:
	rm -rf dist
	uv build

twine-check:
	uv run python -m twine check dist/*

package-check: build twine-check

clean:
	rm -rf dist build .coverage coverage.xml .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
