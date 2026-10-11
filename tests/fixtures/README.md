# Test fixtures

Error fixtures are synthetic, fake-only envelopes following the Error/code/message
shape in E*TRADE's API documentation. They are not network recordings and do not
establish sandbox or production verification.

Response fixtures under `responses/` use fake/example broker data converted to
JSON from E*TRADE-shaped fixture payloads. Do not store real broker account data,
real credentials, OAuth tokens, authorization verifiers, or account identifiers
here.

`documented_response_fields.json` records the response field names and types from
the official Portfolio, Quote, and Orders documentation reviewed on 2026-10-10.
The matching `documented_model_samples.json` and complete response fixtures are
synthetic examples covering those fields, not production recordings. They test
field coverage, nested types, numeric/date conversion, and schema representation.
Fields prefixed with `future` deliberately exercise unknown-field preservation.
