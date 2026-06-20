"""Tests for the live Home Assistant smoke-test wrapper."""

from __future__ import annotations

import ast
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import urllib.error
import urllib.parse

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_smoke_script_source() -> str:
    """Extract the embedded Playwright script without importing the wrapper."""
    module = ast.parse((ROOT / "scripts" / "smoke_ha_frontend.py").read_text())
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "SCRIPT":
                value = ast.literal_eval(node.value)
                if not isinstance(value, str):
                    raise AssertionError("SCRIPT must be a string literal")
                return value
    raise AssertionError("SCRIPT assignment not found")


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location(
        "smoke_ha_frontend",
        ROOT / "scripts" / "smoke_ha_frontend.py",
    )
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load smoke_ha_frontend.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.status = 200
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()


def test_embedded_smoke_script_has_valid_node_syntax(tmp_path: Path) -> None:
    """The embedded Playwright script should fail fast on JavaScript syntax errors."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    script_path = tmp_path / "smoke.js"
    script_path.write_text(_load_smoke_script_source(), encoding="utf-8")

    result = subprocess.run(
        [node, "--check", str(script_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_auth_flow_login_uses_home_assistant_client_id(monkeypatch) -> None:
    """The auth-flow token helper should match Home Assistant's login API shape."""
    module = _load_smoke_module()
    requests = []
    responses = [
        {"flow_id": "flow-1"},
        {"type": "create_entry", "result": "auth-code"},
        {"access_token": "access-token", "refresh_token": "refresh-token"},
    ]

    def fake_urlopen(request, timeout):
        requests.append(request)
        return _FakeResponse(responses[len(requests) - 1])

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    access_token, refresh_token = module._login_ha_auth_flow(
        "http://homeassistant.local:8123",
        "user",
        "password",
    )

    assert access_token == "access-token"
    assert refresh_token == "refresh-token"
    assert requests[0].full_url.endswith("/auth/login_flow")
    assert json.loads(requests[0].data.decode()) == {
        "client_id": module.DEFAULT_HA_AUTH_CLIENT_ID,
        "handler": ["homeassistant", None],
        "redirect_uri": module.DEFAULT_HA_AUTH_CLIENT_ID,
    }
    assert requests[1].full_url.endswith("/auth/login_flow/flow-1")
    assert json.loads(requests[1].data.decode()) == {
        "client_id": module.DEFAULT_HA_AUTH_CLIENT_ID,
        "username": "user",
        "password": "password",
    }
    assert urllib.parse.parse_qs(requests[2].data.decode()) == {
        "grant_type": ["authorization_code"],
        "code": ["auth-code"],
        "client_id": [module.DEFAULT_HA_AUTH_CLIENT_ID],
    }


def test_refresh_token_revoke_is_best_effort(monkeypatch, capsys) -> None:
    """Unsupported HA token deletion should warn without failing the smoke result."""
    module = _load_smoke_module()

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            400,
            "Bad Request",
            {},
            io.BytesIO(
                b'{"error":"unsupported_grant_type",'
                b'"url":"http://198.51.100.22:8123",'
                b'"token":"refresh-token"}'
            ),
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("HA_SMOKE_URL", "http://198.51.100.22:8123")

    assert (
        module._revoke_ha_refresh_token(
            "http://198.51.100.22:8123",
            "refresh-token",
        )
        is False
    )
    captured = capsys.readouterr()
    assert "198.51.100.22" not in captured.err
    assert "refresh-token" not in captured.err
    assert "<redacted-ip>" in captured.err
    assert "<redacted-token>" in captured.err


def test_refresh_token_revoke_redacts_url_errors(monkeypatch, capsys) -> None:
    """Network revoke warnings should not expose HA URL or refresh token details."""
    module = _load_smoke_module()

    def fake_urlopen(request, timeout):
        raise urllib.error.URLError(
            "http://198.51.100.22:8123 token=refresh-token"
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("HA_SMOKE_URL", "http://198.51.100.22:8123")

    assert (
        module._revoke_ha_refresh_token(
            "http://198.51.100.22:8123",
            "refresh-token",
        )
        is False
    )
    captured = capsys.readouterr()
    assert "198.51.100.22" not in captured.err
    assert "refresh-token" not in captured.err
    assert "<redacted" in captured.err


def test_refresh_token_revoke_uses_home_assistant_payload(monkeypatch) -> None:
    """Refresh-token revocation should use HA's documented form fields."""
    module = _load_smoke_module()
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return _FakeResponse({})

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    assert (
        module._revoke_ha_refresh_token(
            "http://homeassistant.local:8123",
            "refresh-token",
        )
        is True
    )

    assert urllib.parse.parse_qs(requests[0].data.decode()) == {
        "token": ["refresh-token"],
        "action": ["revoke"],
    }


def test_smoke_output_redaction_masks_hosts_and_tokens(monkeypatch) -> None:
    """Smoke logs should not expose host URLs, usernames, passwords, or tokens."""
    module = _load_smoke_module()
    monkeypatch.setenv("HA_SMOKE_URL", "http://198.51.100.22:8123")
    monkeypatch.setenv("HA_SMOKE_USER", "a")
    monkeypatch.setenv("HA_SMOKE_PASSWORD", "secret-value")

    redacted = module._redact_smoke_output(
        "http://198.51.100.22:8123/auth/authorize?state=state-value "
        "https://198.51.100.22:8123/api?token=query-token#frag), "
        "https://198.51.100.22:8123/api?token=abc,def)&state=ghi,jkl#frag "
        "redirect_uri=http%3A%2F%2F198.51.100.22%3A8123%2F "
        "host=homeassistant.local ipv6=[fe80::aabb:ccff:fedd:eeff] "
        "mac=aa:bb:cc:dd:ee:ff "
        "Authorization: Bearer super-secret-token "
        "secondary=eyJheader.payload.signature "
        '"access_token": "access-token" '
        '"friendly_name": "UniFi Drive Private Share" '
        '"target_name": "Private Share" '
        '"target_id": "8ab16324-5061-469f-a37f-c50a24227ceb" '
        '"target_key": "mydrive_8ab16324-5061-469f-a37f-c50a24227ceb" '
        '"snapshot_names": ["Private Snapshot"] '
        '"name": "Private Snapshot" '
        '"description": "Private Description" '
        "sensor.unifi_unas_198_51_100_22_snapshot_inventory "
        "a secret-value"
    )

    assert "198.51.100.22" not in redacted
    assert "198_51_100_22" not in redacted
    assert "state-value" not in redacted
    assert "query-token" not in redacted
    assert "abc,def" not in redacted
    assert "ghi,jkl" not in redacted
    assert "homeassistant.local" not in redacted
    assert "fe80::aabb:ccff:fedd:eeff" not in redacted
    assert "aa:bb:cc:dd:ee:ff" not in redacted
    assert "super-secret-token" not in redacted
    assert "eyJheader.payload.signature" not in redacted
    assert "access-token" not in redacted
    assert "UniFi Drive Private Share" not in redacted
    assert "Private Share" not in redacted
    assert "Private Snapshot" not in redacted
    assert "Private Description" not in redacted
    assert "8ab16324-5061-469f-a37f-c50a24227ceb" not in redacted
    assert "secret-value" not in redacted
    assert "Authorization: Bearer <redacted-token>" in redacted
    assert "snapshot_inventory" in redacted
    assert "<redacted:ha_smoke_user> secret-value" not in redacted
    assert "<redacted:ha_smoke_user>" in redacted
    assert "<redacted-token>" in redacted
    assert "<redacted-ip>" in redacted
    assert "<redacted-host>" in redacted
    assert "<redacted-mac>" in redacted
    assert "<redacted-id>" in redacted


def test_short_secret_redaction_uses_token_boundaries(monkeypatch) -> None:
    """Short env secrets should redact standalone values without rewriting words."""
    module = _load_smoke_module()
    monkeypatch.setenv("HA_SMOKE_PASSWORD", "abc")

    redacted = module._redact_smoke_output(
        "password=abc quoted='abc' keep-notabc keep-abc123"
    )

    assert "password=abc" not in redacted
    assert "quoted='abc'" not in redacted
    assert "keep-notabc" in redacted
    assert "keep-abc123" in redacted
    assert redacted.count("<redacted:ha_smoke_password>") == 2


def test_smoke_run_redacts_failing_subprocess_output(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    """Subprocess failures should exit without leaking captured smoke output."""
    module = _load_smoke_module()
    monkeypatch.setenv("HA_SMOKE_PASSWORD", "secret-value")
    child_env = os.environ.copy()
    child_env["HA_SMOKE_API_TOKEN"] = "q7"
    script = (
        "import os, sys; "
        "print('http://198.51.100.22:8123 Authorization: Bearer token-value'); "
        "print('token=' + os.environ['HA_SMOKE_API_TOKEN'] + ' q7suffix'); "
        "print('198_51_100_22 secret-value', file=sys.stderr); "
        "sys.exit(7)"
    )

    with pytest.raises(SystemExit) as err:
        module._run([sys.executable, "-c", script], tmp_path, env=child_env)

    assert err.value.code == 7
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "198.51.100.22" not in combined
    assert "198_51_100_22" not in combined
    assert "token-value" not in combined
    assert "token=q7" not in combined
    assert "q7suffix" in combined
    assert "secret-value" not in combined
    assert "<redacted-ip>" in combined
    assert "<redacted-token>" in combined


def test_smoke_run_preserves_generic_command_tokens(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    """Command arguments should not be treated as generic secrets."""
    module = _load_smoke_module()
    command = ["node", "smoke.js"]

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            command,
            7,
            stdout="node:internal/modules/cjs/loader\n",
            stderr="smoke.js failed before login\n",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as err:
        module._run(command, tmp_path)

    assert err.value.code == 7
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "node:internal/modules/cjs/loader" in combined
    assert "smoke.js failed before login" in combined


def test_browser_token_fallback_supports_home_assistant_token_shapes(
    tmp_path: Path,
) -> None:
    """Browser token discovery should support both known hassTokens shapes."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    harness = f"""
const assert = require("node:assert/strict");
const vm = require("node:vm");

const script = {json.dumps(_load_smoke_script_source())};
const sandbox = {{
  URL,
  console,
  process: {{ env: {{}} }},
  require: (name) => {{
    if (name === "playwright") {{
      return {{ chromium: {{}} }};
    }}
    if (name === "fs") {{
      return {{ promises: {{}} }};
    }}
    return require(name);
  }},
}};

vm.createContext(sandbox);
vm.runInContext(script.replace(/\\nmain\\(\\)\\.catch\\([\\s\\S]*$/, "\\n"), sandbox);
const collectApiTokenFromBrowser = vm.runInContext(
  "collectApiTokenFromBrowser",
  sandbox
);

async function collect(rawTokens) {{
  sandbox.window = {{
    localStorage: {{
      getItem: (key) => key === "hassTokens" ? JSON.stringify(rawTokens) : "",
    }},
  }};
  return await collectApiTokenFromBrowser(
    {{ evaluate: async (fn, url) => fn(url) }},
    "http://homeassistant.local:8123"
  );
}}

(async () => {{
  assert.equal(
    await collect({{
      access_token: "top-level-token",
      hassUrl: "http://homeassistant.local:8123",
    }}),
    "top-level-token"
  );
  assert.equal(
    await collect({{
      "http://homeassistant.local:8123": {{ access_token: "mapped-token" }},
    }}),
    "mapped-token"
  );
}})().catch((error) => {{
  console.error(error.stack || error.message || String(error));
  process.exit(1);
}});
"""
    harness_path = tmp_path / "token_fallback_test.js"
    harness_path.write_text(harness, encoding="utf-8")

    result = subprocess.run(
        [node, str(harness_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
