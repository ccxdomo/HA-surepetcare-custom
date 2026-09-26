"""L1 (contracts §10): live read-only probe — login, read devices, assert.

Run manually on the local host only, never in CI. Output contains only
ids, profiles and versions — never credentials (contracts §11).

Usage:
    python3 tests/live/l1_read.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402


async def main() -> None:
    env = common.load_env()
    api = common.load_api()
    session, client = common.build_client(api, env)
    try:
        await client.login()
        devices = await client.get_devices()
        flap_id = int(common.require(env, "SUREPETCARE_DEVICE_ID"))
        tag_id = int(common.require(env, "SUREPETCARE_TAG_ID_PINCEAU"))
        device, tag = common.find_tag(devices, flap_id, tag_id)
        if device is None:
            sys.exit(f"L1 FAIL: flap {flap_id} not found in /device (no changes made)")
        if tag is None:
            sys.exit(
                f"L1 FAIL: tag {tag_id} not found on flap {flap_id} (no changes made)"
            )
        profile = tag.get("profile")
        version = tag.get("version")
        if profile not in (2, 3):
            sys.exit(f"L1 FAIL: unexpected profile {profile} for tag {tag_id}")
        print(f"L1 OK | {common.describe_tag(device, tag)}")
    finally:
        await session.close()


asyncio.run(main())