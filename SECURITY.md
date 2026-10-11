# Security

`etrade-python` implements OAuth authentication and brokerage operations, including
order placement, changes, and cancellation. Production mutations affect real
brokerage accounts. The current supported release series is 1.0.x. Security fixes
will be released as updates to that series; use the latest available patch release.

## Reporting vulnerabilities

Do not post credentials, account identifiers, or sensitive logs in public issues.
Use GitHub's private vulnerability reporting feature if it is enabled for the
repository. If no private reporting option is available, open an issue requesting
a private contact without including vulnerability details or sensitive data.
A dedicated security contact has not yet been published.

## Credentials and sessions

- Consumer secrets, OAuth tokens, token secrets, signatures, and verifiers must not
  appear in logs, exception diagnostics, fixtures, or ordinary API response models.
  Secret fields and authorization URLs are hidden in normal representations.
  Explicitly accessing credentials or the authorization URL still reveals them
  for their intended use; callers must handle those values carefully.
- The default persistent store uses the system keyring. Storage protection depends
  on the configured keyring backend; the library does not implement its own
  encryption or silently fall back to plaintext files. Memory storage and custom
  implementations are available through the credential-store protocol.
- SessionManager isolates stored credentials by environment, a SHA-256 fingerprint
  of the consumer key, and profile.
- Local token status is an estimate based on stored lifecycle timestamps, not a
  broker verification call. Active request preparation does not advance usage.
  Completed HTTP 2xx exchanges do, even if later payload parsing fails. Failed or
  cancelled exchanges do not. Explicit renewal contacts the broker, and timestamps
  are persisted only after successful renewal.
- Updates within a session manager are serialized and preserve newer timestamps.
  Late responses do not restore deleted or replaced credentials. Custom stores
  used across multiple processes must provide their own concurrency guarantees.
  If usage persistence fails after a successful API exchange, the library logs a
  sanitized warning and preserves the broker response without retrying it.

## Requests and trading

- Sandbox is the default; production must be configured explicitly. API transport
  paths cannot be arbitrary absolute URLs, and signed SDK exchanges do not follow
  redirects. OAuth operations reject non-2xx responses.
- Broker diagnostics redact known request credentials, including individual OAuth
  header values in encoded and decoded forms, query values, and account routing
  keys. Broker messages may contain other personal information; do not log them
  wholesale. Public exceptions do not attach raw HTTP requests or responses.
- Library logs use static operation labels, timing, and status. Automatic HTTPX
  and current HTTPcore wire loggers are suppressed during SDK exchanges only;
  unrelated requests retain their existing logging configuration. Caller-provided
  clients, event hooks, authenticators, and wire logging remain the application's
  responsibility and must not expose credentials or sensitive account data.
- Preview and placement are separate operations. CLI order mutations require
  explicit confirmation. Selected transient failures may be retried only when
  explicitly classified as safe reads; order mutations are not automatically
  retried. A failed mutation may have succeeded at the broker, so reconcile its
  outcome before considering resubmission.
- Default tests are offline and use fake/example data. Future live integration
  tests must be opt-in, with production tests read-only by default. Sandbox
  responses do not establish production behavior.

The library cannot protect secrets from debuggers that inspect local variables,
malicious extensions, or application code that explicitly extracts and logs them.
It is an unofficial software API client, not financial advice.
