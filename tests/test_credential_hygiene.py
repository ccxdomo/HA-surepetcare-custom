"""T15 (contracts §10): credential hygiene — no repo file contains the secrets.

Loads the secret VALUES at runtime from the environment/secrets file and
scans every repo file for them. Never prints the values: on failure only
file names and env key names are reported. Skipped when the secrets file
is absent (CI never has it, contracts §11).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SECRETS = Path(
    "/home/emc/.openclaw/workspace-codepilot/.secrets/surepetcare.env"
)
# Directories never scanned (build caches; .secrets lives outside the repo).
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".secrets", ".venv", ".ruff_cache"}
# Only credential-like keys are secrets. Device/tag ids are fixture values
# published by the spec set itself (research.md §1, data-model.md §4) and
# the live outputs must show them (contracts §10 L1-L3).
SECRET_KEY_MARKERS = ("EMAIL", "PASSWORD", "TOKEN", "SECRET")


def load_secret_values() -> dict[str, str]:
    source = Path(os.environ.get("SUREPETCARE_SECRETS", DEFAULT_SECRETS))
    if not source.exists():
        pytest.skip("secrets file not present (CI run)")
    values: dict[str, str] = {}
    for raw in source.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        key = key.strip()
        if len(value) >= 6 and any(m in key.upper() for m in SECRET_KEY_MARKERS):
            values[key] = value
    return values


def test_t15_no_credentials_in_repo():
    values = load_secret_values()
    assert values, "secrets file present but no credential keys found"
    offenders: list[str] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        parts = path.relative_to(REPO_ROOT).parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        for key, value in values.items():
            # Compare the raw bytes of the value — no hashing needed since
            # nothing is printed or logged here.
            if value.encode() in content:
                offenders.append(f"{path.relative_to(REPO_ROOT)} (key: {key})")
    assert not offenders, "credential values leaked into repo files: " + "; ".join(
        offenders
    )


def test_t15_secrets_file_permissions():
    """The secrets file stays mode 600 (contracts §11)."""
    source = Path(os.environ.get("SUREPETCARE_SECRETS", DEFAULT_SECRETS))
    if not source.exists():
        pytest.skip("secrets file not present (CI run)")
    mode = source.stat().st_mode & 0o777
    assert mode == 0o600, f"secrets file mode {oct(mode)} != 600"