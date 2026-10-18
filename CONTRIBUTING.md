# Contributing

Use Python 3.11+ and uv. Runtime network code must be async, typed, and use the
shared request pipeline. Keep API services independent of application frameworks.

## Development workflow

Run from the repository root:

```sh
make install
make check
make package-check
```

`make install` creates or synchronizes the virtual environment with development
dependencies. `make check` runs Ruff lint and formatting checks, Pyright, and
pytest. `make package-check` builds the wheel and source distribution and checks
package metadata with Twine.

Use `make format` to apply formatting. Individual checks are available through
`make lint`, `make format-check`, `make type`, and `make test`.

If you need to recreate the environment, `make venv-reset` deletes `.venv`, creates
it with Python 3.12, and reinstalls dependencies. This does not change the library's
Python 3.11+ requirement.

## Implementation and tests

Review the official E*TRADE specification before changing endpoint behavior.
Document the intended public Python API in the pull request and implement it
independently; do not mechanically translate reference implementation code.
Update the README coverage table when endpoint support or verification changes.
Public contributions must not depend on unpublished local documentation.

Use HTTPX MockTransport at the HTTP boundary for contract tests, exercising
request serialization and response parsing into typed models. Keep tests offline
and use fake credentials and customer data. Pin clocks in time-dependent tests.
Follow the provenance and maintenance guidance in [tests/fixtures/README.md](tests/fixtures/README.md)
when adding or converting fixtures.

Coverage includes statements and branches; the configured combined threshold is
90%. Pytest excludes `sandbox` and `production` markers by default. No live
integration tests are currently included. Any future live tests must be explicitly
selected, and production tests must be read-only by default. Never place trades
in ordinary CI.

Test pagination, validation, credential redaction, and retry behavior when changing
those features. Order mutations must not acquire automatic retries.

Credential lifecycle changes must also test independent session managers and
actual subprocess contention. Use synthetic keyring backends and HTTPX
MockTransport; subprocess tests must not access the system keyring or broker.
Cover replacement/deletion, monotonic timestamps, renewal/revocation, cancellation
during keyring workers, lock timeouts, namespace isolation, and process-exit lock
release. A lock must cover the full read/check/update transaction. Report offline
verification separately from authenticated broker validation.

## Package verification and releases

After `make package-check`, verify installation outside the source checkout in a
separate environment:

```sh
wheel_check_dir="$(mktemp -d)"
uv venv --python 3.12 "$wheel_check_dir"
uv pip install --python "$wheel_check_dir/bin/python" dist/*.whl
(cd /tmp && "$wheel_check_dir/bin/python" -c 'import etrade_python; print(etrade_python.__version__)')
(cd /tmp && "$wheel_check_dir/bin/etrade" --version)
```


Contributions are licensed under Apache-2.0. Do not add personal account details,
.env files, live recordings, or credentials. Document the origin and permissions
for reused fixtures or examples; use synthetic data for new security scenarios.
