# Test fixtures

Error fixtures are synthetic, fake-only envelopes following the Error/code/message
shape in E*TRADE's API documentation. They are not network recordings and do not
establish sandbox or production verification.

Response fixtures under `responses/` use fake/example broker data converted to
JSON from E*TRADE-shaped fixture payloads. Do not store real broker account data,
real credentials, OAuth tokens, authorization verifiers, or account identifiers
here.
