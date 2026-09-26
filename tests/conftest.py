"""Shared pytest fixtures for spec 041 tests (repo-root tests/)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT_DIR = REPO_ROOT / "custom_components" / "surepetcare"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_LOADED: dict[str, Any] = {}


def load_standalone(name: str, filename: str) -> Any:
    """Load a component module file without triggering the package __init__.

    api.py / assignments.py / const.py are standalone by contract (no HA
    imports); file-based import proves it without requiring homeassistant.
    """
    if name in _LOADED:
        return _LOADED[name]
    spec = importlib.util.spec_from_file_location(name, COMPONENT_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    _LOADED[name] = module
    return module


@pytest.fixture(scope="session")
def api_module() -> Any:
    """The component's api.py as a standalone module (no package __init__)."""
    return load_standalone("surepetcare_api_041", "api.py")


@pytest.fixture(scope="session")
def assignments_module() -> Any:
    """The component's assignments.py as a standalone module."""
    return load_standalone("surepetcare_assignments_041", "assignments.py")


@pytest.fixture(scope="session")
def const_module() -> Any:
    """The component's const.py as a standalone module (pure constants)."""
    return load_standalone("surepetcare_const_041", "const.py")


@pytest.fixture(scope="session")
def me_start() -> dict:
    """A sanitized /me/start-shaped fixture (data-model.md §4 ids)."""
    with open(Path(__file__).parent / "fixtures" / "me_start.json") as handle:
        return json.load(handle)


@pytest.fixture
def entity_map(me_start: dict) -> dict[int, dict]:
    """A fresh Mapping[int, raw payload] like the coordinator's data.

    Deep-copied per test so profile mutations never leak between tests.
    Values are plain payload dicts (assignments.py duck-types them).
    """
    entities: dict[int, dict] = {}
    for device in me_start["data"]["devices"]:
        entities[device["id"]] = device
    for pet in me_start["data"]["pets"]:
        entities[pet["id"]] = pet
    # Deep copy per test; json round-trip stringifies int keys, so restore them.
    return {int(key): value for key, value in json.loads(json.dumps(entities)).items()}