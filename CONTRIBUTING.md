# Contributing

Use Python 3.11+ and install `.[dev]` in a virtual environment. Runtime code must
be async, typed, and use the shared request pipeline.

Before implementing an endpoint, review its official specification, inspect the
relevant reference-library behavior, document the intended Python API, and add
original fake-only contract fixtures. Do not copy reference implementation code
or tests. Update `docs/api-coverage.md` with actual implementation and verification.

Run from the repository root:

```sh
ruff check .
ruff format --check .
pyright
pytest
python -m build
python -m twine check dist/*
```

Pytest excludes `sandbox` and `production` by default. `pytest -m sandbox` explicitly
selects future sandbox tests; none exist yet. Never place trades in ordinary CI.
Use HTTPX MockTransport at the HTTP boundary rather than mocking service methods.
Require at least 90% branch coverage for implemented code. Use fake secrets only.

Verify installation in a separate environment, outside the source directory:

```sh
python -m venv /tmp/etrade-wheel-check
/tmp/etrade-wheel-check/bin/python -m pip install dist/*.whl
(cd /tmp && /tmp/etrade-wheel-check/bin/python -c 'import etrade_python; print(etrade_python.__version__)')
```

Build the sdist and wheel without importing the package in build metadata. The
release version remains `0.1.0.dev0` until a coherent API is ready. CI builds but
never publishes. A future release workflow should use PyPI Trusted Publishing.

Contributions are licensed under Apache-2.0. Do not add personal account details,
.env files, live recordings, credentials, or copyrighted reference fixtures.
