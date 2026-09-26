"""Shared helpers for the live probe scripts (tests/live/, contracts §10 L1-L3).

Reads credentials from the environment only (a dotenv-style parse of
.secrets/surepetcare.env — values may contain shell-special characters);
never prints, echoes, logs or stores them (contracts §11).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENT_DIR = REPO_ROOT / "custom_components" / "surepetcare"
DEFAULT_SECRETS = Path(
    "/home/emc/.openclaw/workspace-codepilot/.secrets/surepetcare.env"
)


def load_env(path: Path | None = None) -> dict[str, str]:
    """Merge the secrets file under the real environment (env wins)."""
    env = dict(os.environ)
    source = Path(path or os.environ.get("SUREPETCARE_SECRETS", DEFAULT_SECRETS))
    if source.exists():
        for raw in source.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key and value:
                env.setdefault(key, value)
    return env


def require(env: dict[str, str], key: str) -> str:
    value = env.get(key)
    if not value:
        sys.exit(f"missing {key} in environment/secrets file — aborting (no changes made)")
    return value


def load_api():
    """Load the component's api.py standalone (no HA imports needed)."""
    spec = importlib.util.spec_from_file_location(
        "surepetcare_api_live", COMPONENT_DIR / "api.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["surepetcare_api_live"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_client(api, env):
    """Build the client with an injected aiohttp session (lazy login)."""
    import aiohttp

    session = aiohttp.ClientSession()
    client = api.SurePetcareApiClient(
        email=require(env, "SUREPETCARE_EMAIL"),
        password=require(env, "SUREPETCARE_PASSWORD"),
        session=session,
        timeout=60,
    )
    return session, client


def find_tag(devices: list, device_id: int, tag_id: int):
    device = next((d for d in devices if d.get("id") == device_id), None)
    if device is None:
        return None, None
    tag = next(
        (t for t in device.get("tags") or [] if t.get("id") == tag_id), None
    )
    return device, tag


def describe_tag(device, tag) -> str:
    """A sanitized one-line description: ids/profiles/versions only (§11)."""
    return (
        f"device={device.get('id')} name={str(device.get('name') or '').strip()!r} "
        f"online={bool((device.get('status') or {}).get('online'))} "
        f"tag={tag.get('id')} profile={tag.get('profile')} "
        f"version={tag.get('version')} updated_at={tag.get('updated_at')}"
    )