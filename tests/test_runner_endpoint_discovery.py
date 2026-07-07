"""Execution-based tests for multi-program-runner-impl tasks 3.1-3.7
(runner-endpoint-discovery + runner-endpoint-via-launch-settings specs) in
``launch-agents.ps1``.

Unlike the rest of this repo's PS1 coverage (``test_launch_runner_dispatch.py``),
these tests actually execute the PowerShell functions via ``pwsh`` rather than
asserting on the script's text. The function-definitions region of the script
(everything before top-level execution starts at "Load settings, pick active
connection") is dot-sourced into a harness; each test then calls real
functions and asserts on real return values / thrown errors.

Requires ``pwsh`` on PATH. Skipped entirely if absent (this repo's other PS1
tests remain the text-based fallback for environments without a PowerShell
runtime).
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
PS1_LAUNCHER = REPO / "scripts" / "launch-agents.ps1"
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh not available in this environment")


def _function_defs_prefix() -> str:
    """The script text up to (not including) top-level execution."""
    text = PS1_LAUNCHER.read_text(encoding="utf-8")
    marker = "# Load settings, pick active connection"
    idx = text.index(marker)
    return text[:idx]


@pytest.fixture(scope="module")
def harness_path(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("ps1-harness")
    p = d / "harness.ps1"
    p.write_text(_function_defs_prefix(), encoding="utf-8")
    return p


def run_ps(harness_path: Path, body: str, env: dict | None = None) -> dict:
    """Dot-source the harness, run ``body``, and return the JSON-decoded
    ``$result`` hashtable ``body`` is expected to set."""
    script = f'. "{harness_path}"\n{body}\n$result | ConvertTo-Json -Depth 8 -Compress\n'
    script_file = harness_path.parent / "run.ps1"
    script_file.write_text(script, encoding="utf-8")
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    proc = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-File", str(script_file)],
        capture_output=True,
        text=True,
        timeout=30,
        env=full_env,
    )
    assert proc.returncode == 0, f"pwsh failed:\nSTDOUT={proc.stdout}\nSTDERR={proc.stderr}"
    out = proc.stdout.strip().splitlines()
    assert out, f"no output from pwsh; stderr={proc.stderr}"
    return json.loads(out[-1])


# ---------------------------------------------------------------------------
# 3.1 — flat runner_uri / runner_token_source / runner_tls keys parse and
# round-trip through Read-SettingsFile / Save-SettingsFile with no parser
# depth change.
# ---------------------------------------------------------------------------

class TestFlatRunnerKeysRoundTrip:
    def test_flat_keys_parse(self, harness_path, tmp_path):
        settings_file = tmp_path / "launch-settings.yaml"
        settings_file.write_text(
            textwrap.dedent(
                """\
                connections:
                  mesh:
                    ssh_client: native
                    ssh_default_host: user@1.2.3.4
                    ssh_key: ~/.ssh/id_ed25519
                    runner_uri: "runner://:8200"
                    runner_token_source: "ssh-cat:~/.otaman/runner.endpoint"
                    runner_tls: "false"
                """
            ),
            encoding="utf-8",
        )
        body = f"""
        $SettingsFile = "{settings_file}"
        $parsed = Read-SettingsFile
        $conn = $parsed.Connections['mesh']
        $result = @{{
            runner_uri = $conn['runner_uri']
            runner_token_source = $conn['runner_token_source']
            runner_tls = $conn['runner_tls']
            ssh_default_host = $conn['ssh_default_host']
        }}
        """
        r = run_ps(harness_path, body)
        assert r["runner_uri"] == "runner://:8200"
        assert r["runner_token_source"] == "ssh-cat:~/.otaman/runner.endpoint"
        assert r["runner_tls"] == "false"
        assert r["ssh_default_host"] == "user@1.2.3.4"

    def test_flat_keys_round_trip_through_save(self, harness_path, tmp_path):
        settings_file = tmp_path / "launch-settings.yaml"
        body = f"""
        $SettingsFile = "{settings_file}"
        $top = [ordered]@{{ active_connection = 'mesh' }}
        $conns = [ordered]@{{}}
        $conns['mesh'] = [ordered]@{{
            type = 'ssh'
            ssh_default_host = 'user@1.2.3.4'
            runner_uri = 'runner://:8200'
            runner_token_source = 'env:RUNNER_TOKEN'
            runner_tls = 'true'
        }}
        Save-SettingsFile -Top $top -Connections $conns
        $reloaded = Read-SettingsFile
        $conn = $reloaded.Connections['mesh']
        $result = @{{
            runner_uri = $conn['runner_uri']
            runner_token_source = $conn['runner_token_source']
            runner_tls = $conn['runner_tls']
        }}
        """
        r = run_ps(harness_path, body)
        assert r["runner_uri"] == "runner://:8200"
        assert r["runner_token_source"] == "env:RUNNER_TOKEN"
        assert r["runner_tls"] == "true"

    def test_nested_runner_block_children_are_dropped_not_trusted(self, harness_path, tmp_path):
        # Documents the known limitation the spec calls out: a hand-written
        # nested `runner:` map is not a supported input. The 4-space regex
        # matches `runner:` as a scalar (empty value); 6-space children
        # match nothing and are silently dropped.
        settings_file = tmp_path / "launch-settings.yaml"
        settings_file.write_text(
            textwrap.dedent(
                """\
                connections:
                  mesh:
                    ssh_default_host: user@1.2.3.4
                    runner:
                      uri: "runner://:8200"
                      token_source: "env:X"
                """
            ),
            encoding="utf-8",
        )
        body = f"""
        $SettingsFile = "{settings_file}"
        $parsed = Read-SettingsFile
        $conn = $parsed.Connections['mesh']
        $result = @{{
            runner_uri = $conn['runner_uri']
            has_runner_key = $conn.Contains('runner')
            runner_value = $conn['runner']
        }}
        """
        r = run_ps(harness_path, body)
        assert r["runner_uri"] is None
        assert r["has_runner_key"] is True
        assert r["runner_value"] == ""


# ---------------------------------------------------------------------------
# 3.3 — runner_uri dual URI shapes
# ---------------------------------------------------------------------------

class TestResolveRunnerUri:
    def test_explicit_https_used_as_is(self, harness_path):
        body = """
        $settings = @{}
        $r = Resolve-RunnerUri -RunnerUri "https://10.0.0.5:8200" -Settings $settings
        $result = $r
        """
        r = run_ps(harness_path, body)
        assert r == {"Host": "10.0.0.5", "Port": 8200, "Tls": True}

    def test_explicit_http_used_as_is(self, harness_path):
        body = """
        $settings = @{}
        $r = Resolve-RunnerUri -RunnerUri "http://10.0.0.5:8200" -Settings $settings
        $result = $r
        """
        r = run_ps(harness_path, body)
        assert r == {"Host": "10.0.0.5", "Port": 8200, "Tls": False}

    def test_runner_scheme_omitted_host_derives_from_ssh_default_host(self, harness_path):
        body = """
        $settings = @{ ssh_default_host = "dev@1.2.3.4" }
        $r = Resolve-RunnerUri -RunnerUri "runner://:8200" -Settings $settings
        $result = $r
        """
        r = run_ps(harness_path, body)
        assert r == {"Host": "1.2.3.4", "Port": 8200, "Tls": False}

    def test_runner_scheme_with_tls_true_resolves_https(self, harness_path):
        body = """
        $settings = @{ ssh_default_host = "dev@1.2.3.4"; runner_tls = "true" }
        $r = Resolve-RunnerUri -RunnerUri "runner://:8200" -Settings $settings
        $result = $r
        """
        r = run_ps(harness_path, body)
        assert r["Tls"] is True

    def test_runner_scheme_omitted_host_no_ssh_default_host_throws(self, harness_path):
        body = """
        $settings = @{}
        $result = @{ threw = $false }
        try {
            Resolve-RunnerUri -RunnerUri "runner://:8200" -Settings $settings | Out-Null
        } catch {
            $result.threw = $true
            $result.message = "$_"
        }
        """
        r = run_ps(harness_path, body)
        assert r["threw"] is True

    def test_malformed_uri_throws(self, harness_path):
        body = """
        $settings = @{}
        $result = @{ threw = $false }
        try {
            Resolve-RunnerUri -RunnerUri "not-a-uri" -Settings $settings | Out-Null
        } catch {
            $result.threw = $true
        }
        """
        r = run_ps(harness_path, body)
        assert r["threw"] is True


# ---------------------------------------------------------------------------
# 3.2 — 3-state discovery precedence
# ---------------------------------------------------------------------------

class TestResolveRunnerEndpointForConnection:
    def test_from_block_takes_precedence_over_file(self, harness_path, tmp_path, monkeypatch):
        endpoint_dir = tmp_path / "fromblock-precedence"
        (endpoint_dir / ".otaman").mkdir(parents=True)
        (endpoint_dir / ".otaman" / "runner.endpoint").write_text(
            "host=9.9.9.9\nport=9999\ntoken=filetoken\npid=1\n", encoding="utf-8"
        )
        body = """
        $settings = @{ runner_uri = "http://10.0.0.5:8200" }
        $d = Resolve-RunnerEndpointForConnection -Settings $settings
        $result = @{ Source = $d.Source; Host = $d.Endpoint.Host; Port = $d.Endpoint.Port; Token = $d.Endpoint.Token }
        """
        r = run_ps(harness_path, body, env={"HOME": str(endpoint_dir)})
        assert r["Source"] == "FromBlock"
        assert r["Host"] == "10.0.0.5"
        assert r["Token"] is None

    def test_falls_back_to_file_when_no_block(self, harness_path, tmp_path):
        endpoint_dir = tmp_path / "fromfile-fallback"
        (endpoint_dir / ".otaman").mkdir(parents=True)
        (endpoint_dir / ".otaman" / "runner.endpoint").write_text(
            "host=9.9.9.9\nport=9999\ntoken=filetoken\npid=1\n", encoding="utf-8"
        )
        body = """
        $settings = @{}
        $d = Resolve-RunnerEndpointForConnection -Settings $settings
        $result = @{ Source = $d.Source; Host = $d.Endpoint.Host; Token = $d.Endpoint.Token }
        """
        r = run_ps(harness_path, body, env={"HOME": str(endpoint_dir)})
        assert r["Source"] == "FromFile"
        assert r["Host"] == "9.9.9.9"
        assert r["Token"] == "filetoken"

    def test_none_when_neither_source_present(self, harness_path, tmp_path):
        empty_home = tmp_path / "empty-home"
        empty_home.mkdir()
        body = """
        $settings = @{}
        $d = Resolve-RunnerEndpointForConnection -Settings $settings
        $result = @{ Source = $d.Source; Endpoint = $d.Endpoint }
        """
        r = run_ps(harness_path, body, env={"HOME": str(empty_home)})
        assert r["Source"] == "None"
        assert r["Endpoint"] is None


# ---------------------------------------------------------------------------
# 3.5 — Get-NativeSshInvocation (shared client/key/host resolution)
# ---------------------------------------------------------------------------

class TestGetNativeSshInvocation:
    def test_resolves_exe_key_and_target(self, harness_path):
        body = """
        $settings = @{ ssh_default_host = "user@1.2.3.4"; ssh_key = "C:/Users/Roman/.ssh/id_ed25519" }
        $inv = Get-NativeSshInvocation -Settings $settings
        $result = @{ Exe = $inv.Exe; KeyArgs = $inv.KeyArgs; Target = $inv.Target }
        """
        r = run_ps(harness_path, body)
        assert r["Exe"] == "ssh.exe"
        assert r["KeyArgs"] == ["-i", "C:/Users/Roman/.ssh/id_ed25519"]
        assert r["Target"] == "user@1.2.3.4"
        # No WSL path translation -- native ssh.exe wants the Windows-form
        # path unchanged (this is the ab8780c/6123742 regression surface).

    def test_no_key_yields_empty_key_args(self, harness_path):
        body = """
        $settings = @{ ssh_default_host = "user@1.2.3.4" }
        $inv = Get-NativeSshInvocation -Settings $settings
        $result = @{ KeyArgsCount = $inv.KeyArgs.Count }
        """
        r = run_ps(harness_path, body)
        assert r["KeyArgsCount"] == 0

    def test_no_ssh_default_host_throws(self, harness_path):
        body = """
        $settings = @{}
        $result = @{ threw = $false }
        try { Get-NativeSshInvocation -Settings $settings | Out-Null } catch { $result.threw = $true }
        """
        r = run_ps(harness_path, body)
        assert r["threw"] is True


# ---------------------------------------------------------------------------
# 3.4 — runner_token_source resolver grammar
# ---------------------------------------------------------------------------

class TestResolveRunnerToken:
    def test_env_scheme(self, harness_path):
        body = """
        $settings = @{ runner_token_source = "env:MY_TEST_RUNNER_TOKEN" }
        $result = @{ token = Resolve-RunnerToken -Settings $settings }
        """
        r = run_ps(harness_path, body, env={"MY_TEST_RUNNER_TOKEN": "abc123"})
        assert r["token"] == "abc123"

    def test_env_scheme_missing_var_throws(self, harness_path):
        body = """
        $settings = @{ runner_token_source = "env:DOES_NOT_EXIST_XYZ" }
        $result = @{ threw = $false }
        try { Resolve-RunnerToken -Settings $settings | Out-Null } catch { $result.threw = $true }
        """
        r = run_ps(harness_path, body)
        assert r["threw"] is True

    def test_static_scheme(self, harness_path):
        body = """
        $settings = @{ runner_token_source = "static:literal-token-value" }
        $result = @{ token = Resolve-RunnerToken -Settings $settings }
        """
        r = run_ps(harness_path, body)
        assert r["token"] == "literal-token-value"

    def test_dotenv_scheme(self, harness_path, tmp_path):
        dotenv = tmp_path / "secrets.env"
        dotenv.write_text('OTHER=nope\nMY_TOKEN="quoted-value"\n', encoding="utf-8")
        body = f"""
        $settings = @{{ runner_token_source = "dotenv:{dotenv}:MY_TOKEN" }}
        $result = @{{ token = Resolve-RunnerToken -Settings $settings }}
        """
        r = run_ps(harness_path, body)
        assert r["token"] == "quoted-value"

    def test_dotenv_scheme_splits_on_last_colon_for_windows_paths(self, harness_path):
        # The path itself (C:/Users/.../.env) contains a colon from the
        # drive letter. The file won't exist on this Linux test host, but
        # the thrown error must name the correctly-split path, proving the
        # LastIndexOf(':') split (not the naive first-colon split) was used.
        body = """
        $settings = @{ runner_token_source = "dotenv:C:/Users/Roman/.env:MY_TOKEN" }
        $result = @{ threw = $false; message = "" }
        try { Resolve-RunnerToken -Settings $settings | Out-Null }
        catch { $result.threw = $true; $result.message = "$_" }
        """
        r = run_ps(harness_path, body)
        assert r["threw"] is True
        assert "C:/Users/Roman/.env" in r["message"]
        assert "C:/Users/Roman/.env:MY_TOKEN" not in r["message"]

    def test_keyring_scheme_not_yet_implemented(self, harness_path):
        body = """
        $settings = @{ runner_token_source = "keyring:otaman:runner" }
        $result = @{ threw = $false; message = "" }
        try { Resolve-RunnerToken -Settings $settings | Out-Null }
        catch { $result.threw = $true; $result.message = "$_" }
        """
        r = run_ps(harness_path, body)
        assert r["threw"] is True
        assert "keyring" in r["message"].lower()

    def test_unknown_scheme_throws(self, harness_path):
        body = """
        $settings = @{ runner_token_source = "bogus:whatever" }
        $result = @{ threw = $false }
        try { Resolve-RunnerToken -Settings $settings | Out-Null } catch { $result.threw = $true }
        """
        r = run_ps(harness_path, body)
        assert r["threw"] is True

    def test_non_ssh_connection_with_no_token_source_throws(self, harness_path):
        body = """
        $settings = @{ type = "local" }
        $result = @{ threw = $false }
        try { Resolve-RunnerToken -Settings $settings | Out-Null } catch { $result.threw = $true }
        """
        r = run_ps(harness_path, body)
        assert r["threw"] is True


# ---------------------------------------------------------------------------
# 3.5 — ssh-cat reuses the connection's resolved SSH invocation (verified
# end-to-end against a fake ssh.exe that records its argv).
# ---------------------------------------------------------------------------

class TestSshCatReusesResolvedInvocation:
    @pytest.fixture
    def fake_ssh_exe(self, tmp_path):
        """A fake `ssh.exe` on PATH that records its argv and, when the
        remote command is `cat <path>`, echoes canned endpoint-file content
        -- simulating the remote otaman-runner endpoint file without a real
        SSH round-trip."""
        bin_dir = tmp_path / "fakebin"
        bin_dir.mkdir()
        argv_log = tmp_path / "argv.log"
        script = bin_dir / "ssh.exe"
        script.write_text(
            textwrap.dedent(
                f"""\
                #!/bin/bash
                printf '%s\\n' "$@" > "{argv_log}"
                echo "host=9.9.9.9"
                echo "port=9999"
                echo "token=ssh-cat-resolved-token"
                echo "pid=42"
                exit 0
                """
            ),
            encoding="utf-8",
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return {"bin_dir": bin_dir, "argv_log": argv_log}

    def test_ssh_cat_uses_resolved_client_key_and_host(self, harness_path, fake_ssh_exe):
        body = """
        $settings = @{
            ssh_default_host = "user@1.2.3.4"
            ssh_key = "C:/Users/Roman/.ssh/id_ed25519"
            runner_token_source = "ssh-cat:~/.otaman/runner.endpoint"
        }
        $result = @{ token = Resolve-RunnerToken -Settings $settings }
        """
        env = {"PATH": f"{fake_ssh_exe['bin_dir']}:{os.environ.get('PATH', '')}"}
        r = run_ps(harness_path, body, env=env)
        assert r["token"] == "ssh-cat-resolved-token"

        argv = fake_ssh_exe["argv_log"].read_text(encoding="utf-8").splitlines()
        # Exact shape: -i <key> <host> "cat <path>" -- built entirely from
        # Get-NativeSshInvocation's resolution, no ad-hoc re-derivation.
        # The remote command is one joined string (not separate "cat" /
        # path argv elements) specifically so a leading `~` in the remote
        # path is never locally tilde-expanded by PowerShell's native-
        # command argument binder before ssh.exe sees it.
        assert argv == [
            "-i",
            "C:/Users/Roman/.ssh/id_ed25519",
            "user@1.2.3.4",
            "cat ~/.otaman/runner.endpoint",
        ]

    def test_ssh_cat_is_the_default_for_ssh_connections(self, harness_path, fake_ssh_exe):
        # No explicit runner_token_source -- must default to
        # ssh-cat:~/.otaman/runner.endpoint for an ssh-type connection.
        body = """
        $settings = @{
            type = "ssh"
            ssh_default_host = "user@1.2.3.4"
        }
        $result = @{ token = Resolve-RunnerToken -Settings $settings }
        """
        env = {"PATH": f"{fake_ssh_exe['bin_dir']}:{os.environ.get('PATH', '')}"}
        r = run_ps(harness_path, body, env=env)
        assert r["token"] == "ssh-cat-resolved-token"
        argv = fake_ssh_exe["argv_log"].read_text(encoding="utf-8").splitlines()
        assert argv[-1] == "cat ~/.otaman/runner.endpoint"

    def test_ssh_cat_remote_failure_propagates(self, harness_path, tmp_path):
        bin_dir = tmp_path / "fakebin-fail"
        bin_dir.mkdir()
        script = bin_dir / "ssh.exe"
        script.write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        body = """
        $settings = @{
            ssh_default_host = "user@1.2.3.4"
            runner_token_source = "ssh-cat:~/.otaman/runner.endpoint"
        }
        $result = @{ threw = $false }
        try { Resolve-RunnerToken -Settings $settings | Out-Null } catch { $result.threw = $true }
        """
        env = {"PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}
        r = run_ps(harness_path, body, env=env)
        assert r["threw"] is True


# ---------------------------------------------------------------------------
# 3.6 — token cached once per launch batch, per connection
# ---------------------------------------------------------------------------

class TestTokenCaching:
    def test_second_call_reuses_cached_value(self, harness_path):
        body = """
        $settings = @{ runner_token_source = "env:CACHE_TEST_TOKEN" }
        $first = Get-CachedRunnerToken -ConnectionName "mesh" -Settings $settings
        [Environment]::SetEnvironmentVariable("CACHE_TEST_TOKEN", "changed-after-first-call")
        $second = Get-CachedRunnerToken -ConnectionName "mesh" -Settings $settings
        $result = @{ first = $first; second = $second }
        """
        r = run_ps(harness_path, body, env={"CACHE_TEST_TOKEN": "original-value"})
        assert r["first"] == "original-value"
        assert r["second"] == "original-value", "second call must reuse the cached token, not re-resolve"

    def test_cache_is_independent_per_connection(self, harness_path):
        body = """
        $meshSettings = @{ runner_token_source = "static:mesh-token" }
        $lanSettings = @{ runner_token_source = "static:lan-token" }
        $mesh = Get-CachedRunnerToken -ConnectionName "mesh" -Settings $meshSettings
        $lan = Get-CachedRunnerToken -ConnectionName "lan" -Settings $lanSettings
        $result = @{ mesh = $mesh; lan = $lan }
        """
        r = run_ps(harness_path, body)
        assert r["mesh"] == "mesh-token"
        assert r["lan"] == "lan-token"


# ---------------------------------------------------------------------------
# 3.7 — degradation-mode behaviour (direct SSH when no runner) is unchanged
# ---------------------------------------------------------------------------

class TestDegradationModeUnchanged:
    def test_no_runner_switch_still_declared(self):
        text = PS1_LAUNCHER.read_text(encoding="utf-8")
        assert "[switch]$NoRunner" in text

    def test_allow_direct_fallback_switch_declared(self):
        text = PS1_LAUNCHER.read_text(encoding="utf-8")
        assert "[switch]$AllowDirectFallback" in text

    def test_unconfigured_runner_degrades_without_flag_requirement(self, harness_path):
        # Source = None (no runner_uri, no endpoint file) must not require
        # -AllowDirectFallback -- this is the "not every developer runs a
        # runner" path and must stay silent-but-informational.
        empty_home = None
        body = """
        $settings = @{}
        $d = Resolve-RunnerEndpointForConnection -Settings $settings
        $configuredSource = $d.Source -in @('FromBlock', 'FromFile')
        $result = @{ Source = $d.Source; ConfiguredSource = $configuredSource }
        """
        r = run_ps(harness_path, body, env={"HOME": "/nonexistent-home-for-test"})
        assert r["Source"] == "None"
        assert r["ConfiguredSource"] is False

    def test_configured_runner_is_flagged_as_requiring_fallback_gate(self, harness_path, tmp_path):
        endpoint_dir = tmp_path / "configured-gate"
        (endpoint_dir / ".otaman").mkdir(parents=True)
        (endpoint_dir / ".otaman" / "runner.endpoint").write_text(
            "host=9.9.9.9\nport=9999\ntoken=t\npid=1\n", encoding="utf-8"
        )
        body = """
        $settings = @{}
        $d = Resolve-RunnerEndpointForConnection -Settings $settings
        $configuredSource = $d.Source -in @('FromBlock', 'FromFile')
        $result = @{ Source = $d.Source; ConfiguredSource = $configuredSource }
        """
        r = run_ps(harness_path, body, env={"HOME": str(endpoint_dir)})
        assert r["Source"] == "FromFile"
        assert r["ConfiguredSource"] is True

    def test_dispatch_block_still_gates_on_not_norunner(self):
        text = PS1_LAUNCHER.read_text(encoding="utf-8")
        assert "if (-not $NoRunner) {" in text

    def test_hard_fail_exits_nonzero_without_allow_direct_fallback(self):
        # Structural check: the configured-but-unreachable branches must
        # `exit 1`, not merely warn, when -AllowDirectFallback is absent.
        text = PS1_LAUNCHER.read_text(encoding="utf-8")
        idx = text.index("elseif ($configuredSource -and -not $AllowDirectFallback)")
        snippet = text[idx : idx + 600]
        assert "exit 1" in snippet
