# PCE Secret Visibility + Connection Test — Design

- **Date:** 2026-06-16
- **Issue:** [#657](https://github.com/alexgoller/illumio-pretty-cool-events/issues/657)
- **Status:** Approved, ready for implementation plan

## Problem

Two related gaps on the **Configuration** page:

1. **The PCE API secret never shows in the UI.** There is no field for `pce_api_secret`
   in `config.html` at all — it can only be set via YAML or the
   `PCE_EVENTS_PCE_API_SECRET` env var. A user cannot confirm or set the active PCE
   credential from the web UI.
2. **There is no way to test the PCE connection from the config screen.** A
   `health_check()` exists and runs at startup (logged only); the user cannot validate
   that host / API user / secret / org actually authenticate without saving, reloading,
   and reading logs.

## Goals

- Let the user **set** the PCE API secret from the config UI.
- Let the user **double-check** which secret is loaded — without exposing the full
  plaintext value.
- Let the user **test the PCE connection** from the config screen, against the values
  currently in the form, with clear diagnostics.

## Non-goals (YAGNI)

- No full plaintext reveal of any secret in the browser.
- No persistence of test history / results.
- No change to the existing config export/import masking behavior.
- No CSRF overhaul — tracked separately in the security backlog.

## Key constraints discovered

- The codebase deliberately **never sends secret values to the browser**: config export
  masks secrets as `********`, plugin secrets render as `(set - leave blank to keep)` with
  empty values, and the Web UI auth password shows a `(set)` placeholder. The new field
  must preserve this posture.
- `PCEClient.health_check()` hits `/api/v2/health`, which is **unauthenticated** on the
  PCE. It proves reachability but **not** that the API key is valid. A real credential
  test requires a second, authenticated call.
- An existing `togglePasswordVisibility(elementId)` JS helper and the
  `(set - leave blank to keep)` masked-secret pattern (`plugins.html:57-68`) should be
  reused for consistency.

## Design

### 1. Masked secret hint (backend helper)

A pure function that turns a secret into a non-sensitive recognition hint:

```python
def secret_hint(secret: str) -> str:
    """Non-reversible hint so a user can recognize which secret is loaded.

    Returns bullets + last 4 chars (e.g. "••••3f9a"), or "" when unset.
    Never reveals more than the last 4 characters.
    """
    if not secret:
        return ""
    if len(secret) <= 4:
        return "(set)"
    return "••••" + secret[-4:]
```

- Location: a small util reachable from both the route/template context and tests
  (e.g. `pretty_cool_events/config.py` or a `utils` module — follow existing layout).
- Rationale for **last-4** over a hash fingerprint: the user's goal is to recognize *their*
  key (the one in their password manager). Last-4 is the AWS/Stripe convention and is
  directly recognizable; a hash fingerprint leaks zero key material but the user cannot
  easily compute it for their own copy, so it does not serve the "double-check" goal.

### 2. PCE API Secret field (`config.html`)

Add a masked field to the **PCE Connection** card, mirroring the plugin-secret pattern:

- `type="password"`, `value=""`, `name="pce_api_secret"`.
- Placeholder: `(set - leave blank to keep)` when a secret exists, else
  `Enter PCE API secret`.
- Eye toggle button reusing `togglePasswordVisibility`.
- A help line below showing the recognition hint when set:
  `Current: ••••3f9a` (rendered from `secret_hint(config.pce.pce_api_secret)`).

This closes the "secret never shows" gap: the user can both set the secret and confirm
which one is loaded.

### 3. Save handler (`routes.py` → `config_page` POST)

Add `pce_api_secret` handling that mirrors the existing `httpd_password` logic — only
overwrite when non-empty, so a blank submit preserves the current secret:

```python
new_secret = request.form.get("pce_api_secret", "")
if new_secret:
    config.pce.pce_api_secret = new_secret
```

### 4. Connection test — `POST /api/pce/test`

Auth-required JSON endpoint.

- **Inputs (form or JSON):** `pce` (host), `pce_api_user`, `pce_org`, `pce_timeout`,
  `verify_tls`, `pce_api_secret`. Any field left blank — **especially the secret** —
  falls back to the saved config value.
- Builds a **transient** `PCEClient` with those values. Nothing is persisted.
- Two-step check for good diagnostics:
  1. **Reachability** — `/api/v2/health`. Connect/timeout/TLS errors →
     `ok=false`, message `"PCE unreachable: <reason>"`.
  2. **Auth** — lightweight authenticated call
     `GET /api/v2/orgs/{org}/labels?max_results=1`:
     - `200` → success.
     - `401`/`403` → `"Authentication failed (check API user/secret)"`.
     - `404` → `"Organization {org} not found"`.
     - other → generic message + status code.
- **Response shape:** `{ok: bool, message: str, detail?: str, status?: int, latency_ms?: int}`.

Add a thin `PCEClient.test_connection()` returning this structured result so the route
stays simple and the logic is unit-testable.

**Security:**

- Auth-required (same decorator as other `/api/*` routes).
- The secret is **never echoed back** in the response and **never logged** — log only
  host, api_user, and the result/status.
- TLS-verify failures are surfaced clearly (common with self-signed PCEs).
- CSRF posture matches existing POST `/api/*` endpoints (e.g. `/api/plugins/verify`,
  `/api/config/import`); not expanding that backlog item here.

### 5. Test Connection button (`config.html` + JS)

- A "Test Connection" button inside the PCE Connection card with an adjacent result `div`.
- JS gathers the current form values (`pce`, `pce_api_user`, `pce_org`, `pce_timeout`,
  `pce_api_secret`), POSTs them to `/api/pce/test`, shows a spinner, then renders:
  - green success with `latency_ms`, or
  - red failure with `message` / `detail`.
- Reuse the existing `reloadService()` fetch/render pattern in the same template.

## Data flow

```
config.html form
  ├─ Save Configuration ──► POST /config ──► config_page() ──► persist (secret kept if blank)
  └─ Test Connection ─────► POST /api/pce/test ──► transient PCEClient.test_connection()
                                                   ├─ GET /api/v2/health        (reachable?)
                                                   └─ GET …/orgs/{org}/labels?max_results=1 (auth?)
                                                   ◄─ {ok, message, status, latency_ms}
secret_hint(config.pce.pce_api_secret) ──► "Current: ••••3f9a" rendered in template
```

## Error handling

- Distinguish **unreachable** (connect/timeout/TLS) vs **auth failed** (401/403) vs
  **wrong org** (404) vs **other** (status code) so the message is actionable.
- Timeouts surface the configured timeout value.
- TLS verification failures produce a distinct, clear message.

## Testing

- **Unit — `secret_hint`:** empty → `""`; short (≤4) → `"(set)"`; long → `"••••"+last4`;
  assert it never reveals more than 4 characters.
- **Unit — save handler:** blank `pce_api_secret` preserves the stored secret; a provided
  value updates it.
- **Unit — `/api/pce/test`:** with a mocked/monkeypatched `PCEClient` —
  success (200), unreachable (connect error), auth failed (401), wrong org (404);
  assert the secret never appears in the response body or logs.
- **Manual:** load config page → confirm `Current: ••••xxxx` hint shows → click
  Test Connection against a PCE (and against a bad secret) and confirm diagnostics.

## Files touched (anticipated)

- `pretty_cool_events/config.py` (or util module) — `secret_hint()`.
- `pretty_cool_events/pce_client.py` — `test_connection()`.
- `pretty_cool_events/web/routes.py` — secret save block + `POST /api/pce/test`.
- `pretty_cool_events/web/templates/config.html` — secret field, hint, test button + JS.
- `tests/` — unit tests for the above.
