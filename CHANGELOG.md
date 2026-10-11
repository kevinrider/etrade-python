# Changelog

## Unreleased — planned 1.0.0

### Added

- Async-first Python 3.11+ client with a shared injectable HTTPX transport and
  namespaced Accounts, Portfolio, Transactions, Market, Orders, and Alerts services.
- Typed Pydantic request and response models, Decimal monetary values, and
  standard-library date and datetime values. Unknown response fields are discarded.
- Account listing and balances; portfolio positions and lots; transaction history
  and details; quotes, product lookup, option expirations, and option chains.
- Order listing, separate preview and placement operations, change previews,
  change placement, and cancellation, with validated requests and an order builder.
- Alert listing, details, and deletion.
- OAuth 1.0a signing, browser authorization, token exchange, renewal, and revocation;
  automatic inactivity renewal and daily expiration handling.
- Pluggable memory and system-keyring credential stores with isolation by
  environment, consumer-key fingerprint, and profile.
- Diagnostic Typer CLI and interactive orders demo with quote-based price estimates,
  chain-based strike selection, and paginated expiration selection.
- Structured exceptions, sanitized parser diagnostics, conservative retry policy,
  and operational logging without credentials or signed headers.
- Offline unit and HTTP contract tests, lint and type checks, coverage enforcement,
  wheel/source builds, and CI across Python 3.11–3.14.
- Stable-release workflow with version/tag checks, clean distribution installation
  checks, and PyPI Trusted Publishing through the GitHub `pypi` environment.

### Fixed

- Preserve transaction continuation markers, default sorting to DESC, and remove
  duplicate boundary transactions during automatic pagination. Automatic transaction
  pagination requires a page count of at least two.
- Follow portfolio page numbers and order continuation markers without stopping
  prematurely; detect repeated continuation values.
- Accept Python field names as well as broker aliases in request models, and type
  documented Portfolio, Quote, and Orders response fields.
- Parse supported broker timezone labels and offsets; reject invalid timestamps
  with sanitized errors instead of silently discarding them.
- Validate order actions, quantities, option contracts, required prices, and
  integer identifiers; support the documented EXTO market session.
- Reject unexpected response shapes and order mutation responses missing valid
  confirmation identifiers.
- Correct the iron-condor estimate's credit/debit sign, make the monthly expiration
  default visible and selectable, and allow safely encoded multiword product lookups.

### Security

- Hide authorization URLs in ordinary model representations and redact individual
  OAuth header values, including encoded and decoded forms, from error diagnostics.
- Reject non-2xx OAuth responses without following redirects or reporting renewal
  or revocation success.
- Make explicit renewal contact the broker and record ordinary token usage only
  after completed 2xx exchanges. Preserve newer timestamps and ignore late responses
  for deleted or replaced credentials within a session manager.
- Leave legacy profile-only credential entries untouched and require a new login;
  their environment and consumer ownership cannot be verified.
