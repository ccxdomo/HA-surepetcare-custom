"""L3 (contracts §10): post-round-trip read — final proof artifact.

Re-reads /device and prints the final tag assignment (the Reviewer's
proof that the round trip left the tag at profile 3). Read-only.

Usage:
    python3 tests/live/l3_post_read.py
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
        if tag is None:
            sys.exit(f"L3 FAIL: tag {tag_id} not readable on flap {flap_id}")
        print(f"L3 final | {common.describe_tag(device, tag)}")
        if tag.get("profile") != 3:
            sys.exit(f"L3 FAIL: tag {tag_id} rests at profile {tag.get('profile')} (expected 3)")
        print("L3 OK | resting state verified at profile 3")
    finally:
        await session.close()


asyncio.run(main())