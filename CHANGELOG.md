# Changelog

## 0.1.0.dev0 — Unreleased

- Establish src packaging, Apache-2.0 licensing, typed settings, and async client lifecycle.
- Add injectable shared HTTP transport, explicit retry policy, structured errors,
  JSON/Decimal decoding, defensive error parsing, and sanitized operational logs.
- Add OAuth 1.0a signing, request/access token exchange, renewal, revocation,
  session lifecycle management, memory/keyring credential stores, and auth CLI.
- Add typed Accounts service support for account listing and account balances.
- Add diagnostic Accounts CLI commands for manual read-only API testing.
- Manually verify Accounts list and balance against production.
- Add typed Portfolio and Transactions services with diagnostic CLI commands.
- Track official endpoint coverage and reference research without overstating endpoint support.
- Add offline tests, strict type checks, lint, coverage, and build CI.
- Add typed Market, Orders, and Alerts services.
- Complete documented Portfolio, quote, and order response fields, including
  mutual-fund details, extended-hours quotes, Greeks, and buying-power effects.
  These fields now appear as typed attributes and in normal JSON serialization
  instead of `broker_metadata`.
- Remove `broker_metadata` from all API response models and their JSON schemas.
  Unknown response fields are now discarded; callers must use explicitly typed
  properties. Order-request extra-field support remains unchanged.
- Accept both `quoteStatus` and the documented `quotestatus` portfolio spelling.
- Share supported order values between builders and request models, and accept
  the documented `EXTO` market session.
- Reject unknown order request values, nonpositive or nonfinite quantities,
  incomplete option contracts, invalid applicable prices, and stop-limit orders
  without a limit component before sending requests.
- Require positive Python integers for caller-supplied order, preview, and alert
  IDs; numeric strings, floats, Decimal values, and booleans are rejected.
