# Security

This is pre-alpha financial infrastructure. No released version currently provides
OAuth or brokerage operations. Security fixes target the development branch.

Do not post credentials, account identifiers, or sensitive logs in public issues.
Use the repository host's private vulnerability reporting feature if enabled;
otherwise contact a maintainer privately before sharing sensitive details. This
repository does not yet publish a dedicated security contact.

- Keep consumer secrets, OAuth tokens/secrets/signatures, and verifiers out of logs,
  exception text, fixtures, source control, and ordinary response models.
- Settings use masked secrets and input-free constructor errors. Explicitly calling
  `get_secret_value()` reveals a secret; callers must handle it accordingly.
- Library logs record static operation labels and request timing/status only. Never
  supply user data as an operation label. Injected HTTP clients, event hooks, and
  custom wire logging remain the application's responsibility. Automatic HTTPX
  and current HTTPcore wire loggers are suppressed during SDK exchanges only;
  logging levels and handlers are not changed for unrelated requests.
- Transport errors do not retain raw HTTP requests or responses. Broker diagnostics
  redact known request credentials, query values, and account routing keys. Broker
  messages may still contain other personal information; do not log them wholesale.
- Sandbox is the default; production is explicit. Signed requests cannot follow
  redirects or accept arbitrary absolute URLs through the API transport.
- No persistence exists yet. Future credential stores will isolate profiles and
  environments; keyring will be the default local persistent store, without a
  silent plaintext fallback.
- Retries require explicit read-safety classification. A failed mutation may have
  succeeded at the broker; reconcile its outcome before considering resubmission.
- Default tests are offline. Future production integration tests must be opt-in
  and read-only. Sandbox payloads do not establish production behavior.

The library cannot protect secrets from debuggers that inspect local variables,
malicious caller-provided authenticators/transports, or application code that
explicitly extracts and logs them. Configure these extensions with the same care
as the library itself.
