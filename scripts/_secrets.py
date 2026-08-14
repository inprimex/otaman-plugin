"""Secret resolution chain for otaman.

Resolves secret references declared in launch-settings.yaml (and later
platform.yaml) through a tiered source chain:

    1. Process env  — variable already set in the shell
    2. dotenv       — .otaman/secrets.env or .maestro/secrets.env  # legacy: .maestro/secrets.env supported
    3. keyring      — OS keychain via the keyring package (optional dep)
    4. (post-v1)    — vault / aws-sm / gcp-sm / azure-kv

YAML shape accepted (backwards-compatible short form first):

    # Short form
    bot_token_env: MAESTRO_TG_BOT_PERSONAL  # legacy: MAESTRO_ env var prefix still honored

    # Long form
    bot_token:
      sources:
        - { type: env,     name: MAESTRO_TG_BOT_PERSONAL }  # legacy: MAESTRO_ prefix still honored
        - { type: dotenv,  name: MAESTRO_TG_BOT_PERSONAL }  # legacy: MAESTRO_ prefix still honored
        - { type: keyring, service: maestro, account: tg-personal }  # legacy: maestro keyring service name

Usage:
    from _secrets import SecretRef, resolve, resolve_or_fail

    ref = SecretRef.from_config(config_value_from_yaml)
    value = resolve(ref, maestro_root=Path("/path/to/otaman"))  # legacy: maestro_root param name
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass
class SecretRef:
    """A reference to a secret, resolved via a source chain."""

    sources: list[dict[str, Any]]

    @classmethod
    def from_config(cls, config: Any) -> SecretRef:
        """Build from a YAML config value.

        Accepts:
          - A plain string: equivalent to ``{ sources: [{ type: env, name: <str> }] }``
            (used by the ``bot_token_env: NAME`` short form).
          - A dict with a ``sources`` list: the long form.
          - A dict without ``sources``: treated as a single-source spec.
        """
        if config is None:
            raise ValueError("SecretRef config is None")
        if isinstance(config, str):
            return cls(sources=[{"type": "env", "name": config}])
        if isinstance(config, dict):
            if "sources" in config:
                sources = config["sources"]
                if not isinstance(sources, list):
                    raise ValueError(
                        f"SecretRef 'sources' must be a list, got {type(sources).__name__}"
                    )
                return cls(sources=[dict(s) for s in sources])
            return cls(sources=[dict(config)])
        raise ValueError(f"Invalid SecretRef config: {config!r}")


class SecretSource(Protocol):
    """A source that can resolve a secret reference spec to a value."""

    type_name: str

    def resolve(self, spec: dict[str, Any], context: dict[str, Any]) -> str | None:
        """Return the secret value, or None if this source can't resolve it."""
        ...


class EnvSource:
    """Read from the process environment."""

    type_name = "env"

    def resolve(self, spec: dict[str, Any], context: dict[str, Any]) -> str | None:
        name = spec.get("name")
        if not name:
            return None
        value = os.environ.get(name)
        return value if value else None


class DotenvSource:
    """Read from .otaman/secrets.env (or .maestro/secrets.env) in the otaman root.  # legacy: .maestro/secrets.env supported"""

    type_name = "dotenv"

    def resolve(self, spec: dict[str, Any], context: dict[str, Any]) -> str | None:
        name = spec.get("name")
        if not name:
            return None
        maestro_root = context.get("maestro_root")
        if not maestro_root:
            return None
        # Prefer .otaman/secrets.env; fall back to .maestro/secrets.env  # legacy: .maestro/secrets.env supported
        dotenv_path = Path(maestro_root) / ".otaman" / "secrets.env"
        if not dotenv_path.is_file():
            dotenv_path = (
                Path(maestro_root) / ".maestro" / "secrets.env"
            )  # legacy: .maestro/secrets.env path
        if not dotenv_path.is_file():
            return None
        return _read_dotenv_value(dotenv_path, name)


class KeyringSource:
    """Read from the OS keychain via the ``keyring`` package (optional dep)."""

    type_name = "keyring"

    def resolve(self, spec: dict[str, Any], context: dict[str, Any]) -> str | None:
        try:
            import keyring  # type: ignore[import-not-found]
        except ImportError:
            return None
        service = (
            spec.get("service") or "maestro"
        )  # legacy: maestro keyring service name as fallback
        account = spec.get("account") or spec.get("name")
        if not account:
            return None
        try:
            return keyring.get_password(service, account)
        except Exception:
            return None


def _read_dotenv_value(path: Path, key: str) -> str | None:
    """Minimal .env reader — KEY=VALUE per line, # comments, optional quotes."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() != key:
            continue
        value = v.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        return value if value else None
    return None


def load_dotenv(maestro_root: Path | str) -> dict[str, str]:  # legacy: maestro_root param name
    """Load all KEY=VALUE pairs from .otaman/.maestro/secrets.env. Empty dict if absent.  # legacy: .maestro/secrets.env supported"""
    path = Path(maestro_root) / ".otaman" / "secrets.env"
    if not path.is_file():
        path = Path(maestro_root) / ".maestro" / "secrets.env"  # legacy: .maestro/secrets.env path
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        key = k.strip()
        value = v.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        out[key] = value
    return out


_BUILTIN_SOURCES: dict[str, SecretSource] = {
    "env": EnvSource(),
    "dotenv": DotenvSource(),
    "keyring": KeyringSource(),
}


def register_source(source: SecretSource) -> None:
    """Register an additional source (for extensions like vault, aws-sm)."""
    _BUILTIN_SOURCES[source.type_name] = source


def resolve(
    ref: SecretRef,
    *,
    maestro_root: Path | str | None = None,
) -> str | None:
    """Walk the source chain; first non-empty value wins.

    Returns None if no source supplies a value.
    """
    context: dict[str, Any] = {
        "maestro_root": Path(maestro_root) if maestro_root else None,
    }
    for spec in ref.sources:
        source_type = spec.get("type")
        if not source_type:
            continue
        source = _BUILTIN_SOURCES.get(source_type)
        if source is None:
            continue
        value = source.resolve(spec, context)
        if value:
            return value
    return None


def resolve_or_fail(
    ref: SecretRef,
    *,
    maestro_root: Path | str | None = None,
) -> str:
    """Resolve or raise a descriptive error naming every source tried."""
    value = resolve(ref, maestro_root=maestro_root)
    if value:
        return value
    tried = ", ".join(_describe_source(s) for s in ref.sources) or "(no sources configured)"
    raise RuntimeError(
        f"Secret could not be resolved. Sources tried (in order): {tried}. "
        f"Populate one via process env, .otaman/secrets.env, or OS keychain."  # legacy: .maestro/secrets.env also checked
    )


def _describe_source(spec: dict[str, Any]) -> str:
    t = spec.get("type", "?")
    if t == "keyring":
        return f"keyring:{spec.get('service', 'maestro')}/{spec.get('account', '?')}"  # legacy: maestro keyring service name
    return f"{t}:{spec.get('name', '?')}"
