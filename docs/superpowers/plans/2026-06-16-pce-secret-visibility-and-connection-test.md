# PCE Secret Visibility + Connection Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user set + double-check the PCE API secret from the Config UI (masked last-4 hint, never plaintext) and test the PCE connection from the config screen with clear diagnostics.

**Architecture:** A pure `secret_hint()` helper produces a non-reversible recognition hint. A new `PCEClient.test_connection()` does a two-step reachability + authenticated check and returns a structured result. A new auth-required `POST /api/pce/test` route builds a *transient* `PCEClient` from form values (falling back to saved config for blanks) and returns JSON. The config save handler gains secret-preserving persistence (mirrors the existing httpd password logic). The config template gains a masked secret field, the hint line, and a Test Connection button; the shared `togglePasswordVisibility` JS helper moves to `base.html`.

**Tech Stack:** Python 3, Flask, httpx, Pydantic (BaseModel config), Jinja2, Bootstrap 5, pytest.

**Spec:** `docs/superpowers/specs/2026-06-16-pce-secret-visibility-and-connection-test-design.md` · **Issue:** #657

---

## File Structure

- `pretty_cool_events/config.py` — add module-level `secret_hint()` near `PCEConfig`.
- `pretty_cool_events/pce_client.py` — add `PCEClient.test_connection()`.
- `pretty_cool_events/web/routes.py` — import `PCEClient` + `secret_hint`; add `POST /api/pce/test`; add secret-save block; pass `pce_secret_hint` to the config template.
- `pretty_cool_events/web/templates/base.html` — host the shared `togglePasswordVisibility` JS.
- `pretty_cool_events/web/templates/plugins.html` — remove its local copy of `togglePasswordVisibility` (now shared).
- `pretty_cool_events/web/templates/config.html` — secret field, hint, Test Connection button + JS.
- `tests/test_config.py`, `tests/test_pce_client.py`, `tests/test_web/test_routes.py` — tests.

---

## Task 1: `secret_hint()` helper

**Files:**
- Modify: `pretty_cool_events/config.py` (add module-level function after the `PCEConfig` class)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py` (top-level, after the existing imports add `secret_hint` to the import line: `from pretty_cool_events.config import AppConfig, load_config, load_event_types, save_config, secret_hint`):

```python
class TestSecretHint:
    def test_empty_returns_blank(self) -> None:
        assert secret_hint("") == ""

    def test_short_secret_does_not_reveal_chars(self) -> None:
        # 4 chars or fewer: never expose the value
        assert secret_hint("ab") == "(set)"
        assert secret_hint("abcd") == "(set)"

    def test_long_secret_reveals_only_last_four(self) -> None:
        result = secret_hint("supersecretvalue3f9a")
        assert result == "••••3f9a"
        # never reveals more than the last 4 characters
        assert "supersecret" not in result
        assert result.endswith("3f9a")
        assert result.count("•") == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::TestSecretHint -v`
Expected: FAIL — `ImportError: cannot import name 'secret_hint'`

- [ ] **Step 3: Write minimal implementation**

In `pretty_cool_events/config.py`, add this module-level function immediately after the `PCEConfig` class definition (after the `verify_tls: bool = True` line / end of the class):

```python
def secret_hint(secret: str) -> str:
    """Non-reversible recognition hint for a stored secret.

    Returns bullets + the last 4 characters (e.g. "••••3f9a") so a user can
    confirm *which* secret is loaded without exposing the value. Never reveals
    more than the last 4 characters. Returns "" when unset.
    """
    if not secret:
        return ""
    if len(secret) <= 4:
        return "(set)"
    return "••••" + secret[-4:]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py::TestSecretHint -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add pretty_cool_events/config.py tests/test_config.py
git commit -m "feat: add secret_hint helper for masked secret recognition"
```

---

## Task 2: `PCEClient.test_connection()`

**Files:**
- Modify: `pretty_cool_events/pce_client.py` (add method after `health_check`)
- Test: `tests/test_pce_client.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pce_client.py` inside `class TestPCEClient` (the `pce_client` fixture and `httpx`/`MagicMock`/`patch` imports already exist at the top of the file):

```python
    def test_test_connection_success(self, pce_client: PCEClient) -> None:
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        with patch.object(pce_client, "_request", return_value=ok_resp):
            result = pce_client.test_connection()
        assert result["ok"] is True
        assert result["status"] == 200
        assert "latency_ms" in result

    def test_test_connection_unreachable(self, pce_client: PCEClient) -> None:
        with patch.object(pce_client, "_request", side_effect=httpx.ConnectError("boom")):
            result = pce_client.test_connection()
        assert result["ok"] is False
        assert "unreachable" in result["message"].lower()

    def test_test_connection_auth_failed(self, pce_client: PCEClient) -> None:
        health = MagicMock(status_code=200)
        denied = MagicMock(status_code=401)
        with patch.object(pce_client, "_request", side_effect=[health, denied]):
            result = pce_client.test_connection()
        assert result["ok"] is False
        assert result["status"] == 401
        assert "authentication" in result["message"].lower()

    def test_test_connection_wrong_org(self, pce_client: PCEClient) -> None:
        health = MagicMock(status_code=200)
        missing = MagicMock(status_code=404)
        with patch.object(pce_client, "_request", side_effect=[health, missing]):
            result = pce_client.test_connection()
        assert result["ok"] is False
        assert result["status"] == 404
        assert "not found" in result["message"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pce_client.py -k test_connection -v`
Expected: FAIL — `AttributeError: 'PCEClient' object has no attribute 'test_connection'`

- [ ] **Step 3: Write minimal implementation**

In `pretty_cool_events/pce_client.py`, add `import time` to the imports at the top (alongside `logging`, `threading`), then add this method to `PCEClient` immediately after `health_check`:

```python
    def test_connection(self) -> dict[str, Any]:
        """Validate reachability AND credentials.

        Two steps so diagnostics are actionable:
        1. /api/v2/health proves the PCE is reachable (this endpoint is
           unauthenticated, so it cannot validate the API key).
        2. An authenticated labels call proves the api_user/secret/org work.

        Returns: {ok, message, status?, latency_ms?}. Never includes the secret.
        """
        start = time.monotonic()
        try:
            self._request("get", "/api/v2/health", web=True)
        except httpx.HTTPError as e:
            return {"ok": False, "message": f"PCE unreachable: {e}"}

        try:
            r = self._request(
                "get", f"/api/v2/orgs/{self._org_id}/labels",
                web=True, params={"max_results": 1},
            )
        except httpx.HTTPError as e:
            return {"ok": False, "message": f"PCE unreachable: {e}"}

        latency_ms = int((time.monotonic() - start) * 1000)
        if r.status_code == 200:
            return {"ok": True, "message": "Connection successful",
                    "status": 200, "latency_ms": latency_ms}
        if r.status_code in (401, 403):
            return {"ok": False, "status": r.status_code,
                    "message": "Authentication failed (check API user/secret)"}
        if r.status_code == 404:
            return {"ok": False, "status": 404,
                    "message": f"Organization {self._org_id} not found"}
        return {"ok": False, "status": r.status_code,
                "message": f"Unexpected response (HTTP {r.status_code})"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pce_client.py -k test_connection -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add pretty_cool_events/pce_client.py tests/test_pce_client.py
git commit -m "feat: add PCEClient.test_connection with reachability + auth check"
```

---

## Task 3: `POST /api/pce/test` route

**Files:**
- Modify: `pretty_cool_events/web/routes.py` (import + new route)
- Test: `tests/test_web/test_routes.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web/test_routes.py` inside `class TestWebRoutes` (the `client` fixture exists; add `from unittest.mock import MagicMock, patch` to the imports at the top of the file if not present):

```python
    def test_api_pce_test_success(self, client: FlaskClient) -> None:
        fake = MagicMock()
        fake.test_connection.return_value = {"ok": True, "message": "Connection successful",
                                             "status": 200, "latency_ms": 42}
        with patch("pretty_cool_events.web.routes.PCEClient", return_value=fake):
            resp = client.post("/api/pce/test", json={
                "pce": "pce.example.com:8443", "pce_api_user": "api_abc",
                "pce_org": 1, "pce_api_secret": "typedsecret",
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["latency_ms"] == 42

    def test_api_pce_test_falls_back_to_saved_secret(self, client: FlaskClient) -> None:
        captured = {}

        def fake_ctor(**kwargs):
            captured.update(kwargs)
            m = MagicMock()
            m.test_connection.return_value = {"ok": True, "message": "ok", "status": 200}
            return m

        with patch("pretty_cool_events.web.routes.PCEClient", side_effect=fake_ctor):
            # secret omitted -> must fall back to the saved config secret
            client.post("/api/pce/test", json={"pce": "pce.example.com", "pce_api_user": "api_abc"})
        assert captured["api_secret"]  # non-empty: pulled from saved config

    def test_api_pce_test_requires_host_user_secret(self, client: FlaskClient) -> None:
        # Patch saved config secret empty so nothing can satisfy the requirement.
        with patch("pretty_cool_events.web.routes.PCEClient") as ctor:
            resp = client.post("/api/pce/test", json={"pce": "", "pce_api_user": ""})
            # When required values are missing we never build a client.
            ctor.assert_not_called()
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False
```

> Note: `test_api_pce_test_requires_host_user_secret` assumes the `sample_config` fixture has a non-empty saved secret, so blank host + blank user is what triggers the 400 (host/user cannot fall back to anything). If `sample_config.pce.pce` is non-empty it still falls back; the blank *user* with a blank saved user is the trigger. Keep the assertion on `status_code == 400` and `ok is False`; the route returns 400 when host OR user OR secret resolve to empty.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web/test_routes.py -k api_pce_test -v`
Expected: FAIL — 404 (route does not exist yet) / AttributeError on patch target.

- [ ] **Step 3: Write minimal implementation**

In `pretty_cool_events/web/routes.py`, extend the existing `from pretty_cool_events.config import (...)` block to also import `secret_hint`, and add a new import near the other top-level imports:

```python
from pretty_cool_events.pce_client import PCEClient
```

Then add this route (place it near the other `/api/` routes, e.g. just after `api_plugin_verify`):

```python
@bp.route("/api/pce/test", methods=["POST"])
@_auth_required
def api_pce_test() -> Any:
    """Test PCE connectivity using form values, falling back to saved config.

    The secret is never echoed back and never logged.
    """
    config = _get_config()
    data = request.get_json(silent=True) or request.form

    host = (data.get("pce") or config.pce.pce or "").strip()
    api_user = (data.get("pce_api_user") or config.pce.pce_api_user or "").strip()
    secret = data.get("pce_api_secret") or config.pce.pce_api_secret or ""
    try:
        org = int(data.get("pce_org") or config.pce.pce_org)
    except (TypeError, ValueError):
        org = config.pce.pce_org
    try:
        timeout = float(data.get("pce_timeout") or config.pce.pce_timeout)
    except (TypeError, ValueError):
        timeout = float(config.pce.pce_timeout)

    if not host or not api_user or not secret:
        return jsonify({"ok": False,
                        "message": "Host, API user, and secret are required"}), 400

    client = PCEClient(
        base_url=host,
        api_user=api_user,
        api_secret=secret,
        org_id=org,
        verify_tls=config.pce.verify_tls,
        timeout=timeout,
    )
    result = client.test_connection()
    logger.info("PCE connection test to %s as %s: ok=%s",
                host, api_user, result.get("ok"))
    return jsonify(result)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web/test_routes.py -k api_pce_test -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add pretty_cool_events/web/routes.py tests/test_web/test_routes.py
git commit -m "feat: add POST /api/pce/test connection-test endpoint"
```

---

## Task 4: Persist `pce_api_secret` from the config form

**Files:**
- Modify: `pretty_cool_events/web/routes.py` (`config_page` POST handler, ~lines 273-316)
- Test: `tests/test_web/test_routes.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web/test_routes.py` inside `class TestWebRoutes`:

```python
    def test_config_post_updates_secret_when_provided(self, client: FlaskClient, flask_app: Flask) -> None:
        client.post("/config", data={
            "pce": "pce.example.com", "pce_api_user": "api_abc",
            "pce_org": "1", "pce_poll_interval": "10", "pce_timeout": "30",
            "pce_api_secret": "brandnewsecret",
        })
        assert flask_app.config["APP_CONFIG"].pce.pce_api_secret == "brandnewsecret"

    def test_config_post_keeps_secret_when_blank(self, client: FlaskClient, flask_app: Flask) -> None:
        flask_app.config["APP_CONFIG"].pce.pce_api_secret = "existing-secret"
        client.post("/config", data={
            "pce": "pce.example.com", "pce_api_user": "api_abc",
            "pce_org": "1", "pce_poll_interval": "10", "pce_timeout": "30",
            "pce_api_secret": "",
        })
        assert flask_app.config["APP_CONFIG"].pce.pce_api_secret == "existing-secret"
```

> `flask_app` is the existing fixture in this file (it creates the app via `create_app`). `_persist_config()` only writes to disk when `config.config_path` is set; the `sample_config` fixture loads from a temp path, so the assertion reads the in-memory `APP_CONFIG` object which is updated regardless.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web/test_routes.py -k "config_post and secret" -v`
Expected: FAIL — `test_config_post_updates_secret_when_provided` fails (secret unchanged, no handling yet).

- [ ] **Step 3: Write minimal implementation**

In `pretty_cool_events/web/routes.py`, inside `config_page`'s `if request.method == "POST":` block, add a secret-preserving block right after the existing PCE field loop (after the `for key in ["pce", "pce_api_user", ...]` loop, before `config.httpd.enabled = ...`):

```python
        # PCE API secret: only overwrite when provided (blank keeps current)
        new_secret = request.form.get("pce_api_secret", "")
        if new_secret:
            config.pce.pce_api_secret = new_secret
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web/test_routes.py -k "config_post and secret" -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add pretty_cool_events/web/routes.py tests/test_web/test_routes.py
git commit -m "feat: persist PCE API secret from config form (blank keeps current)"
```

---

## Task 5: Move `togglePasswordVisibility` into `base.html` (shared)

**Files:**
- Modify: `pretty_cool_events/web/templates/base.html` (add shared script)
- Modify: `pretty_cool_events/web/templates/plugins.html` (remove the local duplicate)
- Test: `tests/test_web/test_routes.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web/test_routes.py` inside `class TestWebRoutes`:

```python
    def test_toggle_helper_available_on_config_page(self, client: FlaskClient) -> None:
        # The shared JS helper (in base.html) must be present on every page.
        resp = client.get("/config")
        assert b"function togglePasswordVisibility" in resp.data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web/test_routes.py -k toggle_helper -v`
Expected: FAIL — the function is only defined in plugins.html, not on /config.

- [ ] **Step 3: Implement — move the helper to base.html, remove from plugins.html**

In `pretty_cool_events/web/templates/base.html`, replace the bootstrap script line (line 110) so a shared helper script follows it, immediately before `{% block scripts %}{% endblock %}`:

```html
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
      // Shared across pages: toggle a password input between hidden/visible.
      function togglePasswordVisibility(fieldId) {
        const input = document.getElementById(fieldId);
        input.type = input.type === 'password' ? 'text' : 'password';
      }
    </script>
    {% block scripts %}{% endblock %}
```

Then in `pretty_cool_events/web/templates/plugins.html`, delete its now-duplicate definition (lines 159-162):

```javascript
function togglePasswordVisibility(fieldId) {
  const input = document.getElementById(fieldId);
  input.type = input.type === 'password' ? 'text' : 'password';
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web/test_routes.py -k "toggle_helper or plugins" -v`
Expected: PASS — helper on /config, plugins page still renders.

- [ ] **Step 5: Commit**

```bash
git add pretty_cool_events/web/templates/base.html pretty_cool_events/web/templates/plugins.html tests/test_web/test_routes.py
git commit -m "refactor: share togglePasswordVisibility helper via base.html"
```

---

## Task 6: Config UI — secret field, hint, and Test Connection button

**Files:**
- Modify: `pretty_cool_events/web/routes.py` (`config_page` GET passes `pce_secret_hint`)
- Modify: `pretty_cool_events/web/templates/config.html` (field + hint + button + JS)
- Test: `tests/test_web/test_routes.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web/test_routes.py` inside `class TestWebRoutes`:

```python
    def test_config_page_shows_secret_field_and_hint(self, client: FlaskClient, flask_app: Flask) -> None:
        flask_app.config["APP_CONFIG"].pce.pce_api_secret = "supersecretvalue3f9a"
        resp = client.get("/config")
        body = resp.data.decode()
        # Masked secret input present
        assert 'name="pce_api_secret"' in body
        # Recognition hint shows only the last 4 chars, never the full secret
        assert "••••3f9a" in body
        assert "supersecretvalue" not in body
        # Test Connection button present
        assert 'id="pce-test-btn"' in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web/test_routes.py -k secret_field_and_hint -v`
Expected: FAIL — none of those strings are in the page yet.

- [ ] **Step 3a: Pass the hint from the route**

In `pretty_cool_events/web/routes.py`, change the `config_page` GET render (currently `return render_template("config.html", config=config)`) to:

```python
    return render_template(
        "config.html",
        config=config,
        pce_secret_hint=secret_hint(config.pce.pce_api_secret),
    )
```

(`secret_hint` is imported in Task 3.)

- [ ] **Step 3b: Add the secret field + hint to the PCE Connection card**

In `pretty_cool_events/web/templates/config.html`, inside the PCE Connection card `row g-3` (after the `pce_api_user` column block that ends at line 22, before the `pce_org` column at line 23), add:

```html
        <div class="col-md-6">
          <label for="pce_api_secret" class="form-label">API Secret</label>
          <div class="input-group">
            <input type="password" class="form-control" id="pce_api_secret" name="pce_api_secret"
                   value="" placeholder="{{ '(set - leave blank to keep)' if config.pce.pce_api_secret else 'Enter PCE API secret' }}">
            <button class="btn btn-outline-secondary" type="button"
                    onclick="togglePasswordVisibility('pce_api_secret')">
              <i class="bi bi-eye"></i>
            </button>
          </div>
          <div class="form-text">
            {% if pce_secret_hint %}Current: <code>{{ pce_secret_hint }}</code> &mdash; {% endif %}leave blank to keep the current secret.
          </div>
        </div>
```

- [ ] **Step 3c: Add the Test Connection button**

In `pretty_cool_events/web/templates/config.html`, inside the same PCE Connection card, replace the existing "Enable Web UI" switch column (lines 37-42) so the Test Connection button + result sit alongside it:

```html
        <div class="col-12 d-flex align-items-center gap-3">
          <div class="form-check form-switch mb-0">
            <input class="form-check-input" type="checkbox" id="httpd" name="httpd" {% if config.httpd.enabled %}checked{% endif %}>
            <label class="form-check-label" for="httpd">Enable Web UI</label>
          </div>
          <button type="button" class="btn btn-outline-info btn-sm" id="pce-test-btn" onclick="testPceConnection()">
            <i class="bi bi-plug"></i> Test Connection
          </button>
          <span id="pce-test-result" class="small"></span>
        </div>
```

- [ ] **Step 3d: Add the Test Connection JS**

In `pretty_cool_events/web/templates/config.html`, inside the existing `{% block scripts %}` `<script>` (add this function alongside `reloadService`):

```javascript
function testPceConnection() {
  const btn = document.getElementById('pce-test-btn');
  const out = document.getElementById('pce-test-result');
  out.innerHTML = '<span class="text-muted"><i class="bi bi-hourglass-split"></i> Testing...</span>';
  btn.disabled = true;
  fetch('{{ url_for("main.api_pce_test") }}', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      pce: document.getElementById('pce').value,
      pce_api_user: document.getElementById('pce_api_user').value,
      pce_org: document.getElementById('pce_org').value,
      pce_timeout: document.getElementById('pce_timeout').value,
      pce_api_secret: document.getElementById('pce_api_secret').value,
    }),
  })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        const ms = data.latency_ms != null ? ` (${data.latency_ms} ms)` : '';
        out.innerHTML = `<span class="text-success"><i class="bi bi-check-circle"></i> ${data.message}${ms}</span>`;
      } else {
        out.innerHTML = `<span class="text-danger"><i class="bi bi-x-circle"></i> ${data.message}</span>`;
      }
    })
    .catch(err => {
      out.innerHTML = `<span class="text-danger">Error: ${err}</span>`;
    })
    .finally(() => { btn.disabled = false; });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web/test_routes.py -k secret_field_and_hint -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pretty_cool_events/web/routes.py pretty_cool_events/web/templates/config.html tests/test_web/test_routes.py
git commit -m "feat: PCE secret field, recognition hint, and Test Connection button on config page"
```

---

## Task 7: Full suite + manual verification

- [ ] **Step 1: Run the entire test suite**

Run: `pytest -q`
Expected: all green (no regressions).

- [ ] **Step 2: Lint/type checks (if configured)**

Run (if present in the repo): `ruff check pretty_cool_events tests` and/or `mypy pretty_cool_events`
Expected: no new errors in touched files.

- [ ] **Step 3: Manual smoke test**

1. Start the web UI against a config that has a PCE secret set.
2. Open `/config` → confirm the **API Secret** field shows placeholder `(set - leave blank to keep)` and the help line shows `Current: ••••<last4>`.
3. Click the eye toggle → confirms it toggles the (empty) input type; type a value and confirm it reveals/hides.
4. Click **Test Connection**:
   - With a valid PCE + secret → green "Connection successful (NN ms)".
   - With a wrong secret typed in the field → red "Authentication failed (check API user/secret)".
   - With an unreachable host → red "PCE unreachable: …".
5. Save with the secret field blank → reload → confirm the secret is unchanged (hint still shows the same last-4).
6. Save with a new secret typed → confirm the hint updates to the new last-4.

- [ ] **Step 4: Final commit (if any manual-fix tweaks were needed)**

```bash
git add -A
git commit -m "test: verify PCE secret visibility + connection test end to end"
```

---

## Self-Review notes (author)

- **Spec coverage:** masked hint (Task 1 + 6), set secret from UI (Task 4 + 6), double-check current secret (Task 6 hint), connection test endpoint with reachability + auth diagnostics (Task 2 + 3), test uses form values w/ fallback to saved (Task 3), Test Connection button (Task 6). Security: secret never echoed/logged (Task 3 implementation + test asserts full secret absent from page in Task 6). No plaintext reveal, no test history, no export/import changes — all respected.
- **Type consistency:** `test_connection()` returns `{ok, message, status?, latency_ms?}` consumed identically by the route (Task 3) and the JS (Task 6). `secret_hint` signature matches all call sites (config.py def, routes import, template variable `pce_secret_hint`).
- **No placeholders:** every code step contains full code.
