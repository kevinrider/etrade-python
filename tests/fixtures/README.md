# Test fixtures

Error fixtures are synthetic, fake-only envelopes following the Error/code/message
shape in E*TRADE's API documentation. They are not network recordings and do not
establish sandbox or production verification.

Response fixtures under `responses/` include converted reference-library payloads
and synthetic examples shaped from official E*TRADE documentation. All payloads
are stored as JSON with fake/example broker data. These fixtures are not live
recordings or evidence of production verification. Do not store real customer
account data, credentials, OAuth tokens, authorization verifiers, or customer
account identifiers here.

`documented_response_fields.json` records the response field names and types from
the official Portfolio, Quote, and Orders documentation reviewed on 2026-10-10.
The matching `documented_model_samples.json` and complete response fixtures are
synthetic examples covering those fields, not production recordings. They test
field coverage, nested types, numeric/date conversion, and schema representation.
Fields prefixed with `future` deliberately exercise unknown-field discard behavior.

## Maintaining fixtures

- Record the source and any conversion or sanitization in the pull request when
  adding a fixture. Check reuse permissions and preserve any required attribution.
  Do not describe converted reference payloads as original synthetic examples.
- Keep credentials and customer identifiers fake, and use fixed timestamps.
  Inject a fixed clock in tests that interpret expiration or inactivity.
- Exercise fixtures through the HTTP transport and service parser for contract
  tests. Add synthetic payloads for malformed responses, empty collections,
  redaction, and pagination boundaries rather than modifying a normal fixture
  to hide an API behavior.
- When expanding the documented field inventory, update its review date and
  matching samples, then verify typed attributes, conversions, and JSON schemas.
