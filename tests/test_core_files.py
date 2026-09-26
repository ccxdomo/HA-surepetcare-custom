"""Fork-baseline integrity checks (plan.md Phase 0, research.md §8).

- The untouched CORE files keep the byte sizes pinned in research.md §8.
- api.py and assignments.py contain no homeassistant/surepy imports
  (standalone-importable by contract).
- The duplicated module constants stay in sync with const.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT_DIR = REPO_ROOT / "custom_components" / "surepetcare"

# Byte sizes pinned in research.md §8 (fork base: core dev @ 2026-09-26):
# the five files the contract forbids touching (CORE verbatim).
CORE_FILE_SIZES = {
    "binary_sensor.py": 5035,
    "config_flow.py": 3886,
    "entity.py": 1854,
    "lock.py": 3221,
    "sensor.py": 6154,
}

FORBIDDEN_ROOTS = ("homeassistant", "surepy")


def test_core_files_byte_sizes_match_pin():
    for name, expected in CORE_FILE_SIZES.items():
        actual = (COMPONENT_DIR / name).stat().st_size
        assert actual == expected, f"{name}: {actual} bytes != pinned {expected}"


def test_api_and_assignments_standalone_imports():
    for name in ("api.py", "assignments.py"):
        tree = ast.parse((COMPONENT_DIR / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert root not in FORBIDDEN_ROOTS, (
                        f"{name} imports forbidden module {alias.name!r}"
                    )
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert root not in FORBIDDEN_ROOTS, (
                    f"{name} imports from forbidden module {node.module!r}"
                )


def test_constants_consistent(const_module, api_module, assignments_module):
    """const.py is canonical; the standalone mirrors must not drift."""
    assert const_module.PROFILE_INDOOR_ONLY == 3
    assert const_module.PROFILE_NORMAL_ACCESS == 2
    assert assignments_module.PROFILE_INDOOR_ONLY == const_module.PROFILE_INDOOR_ONLY
    assert api_module.VERIFY_ATTEMPTS == const_module.INDOOR_ONLY_VERIFY_ATTEMPTS
    assert (
        api_module.VERIFY_RETRY_SECONDS
        == const_module.INDOOR_ONLY_VERIFY_RETRY_SECONDS
    )


def test_manifest_custom_requirements():
    """Custom manifest per contracts §3: version, documentation, codeowners."""
    import json

    manifest = json.loads((COMPONENT_DIR / "manifest.json").read_text())
    assert manifest["domain"] == "surepetcare"
    assert manifest["version"] == "0.1.0"
    assert manifest["documentation"] == "https://github.com/ccxdomo/HA-surepetcare-custom"
    assert manifest["codeowners"] == ["@ccxdomo", "@benleb", "@danielhiversen"]
    assert manifest["requirements"] == ["surepy==0.9.0"]
    assert manifest["config_flow"] is True
    assert manifest["integration_type"] == "hub"
    assert manifest["iot_class"] == "cloud_polling"
    assert manifest["loggers"] == ["rich", "surepy"]