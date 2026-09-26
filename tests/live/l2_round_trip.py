"""L2 (contracts §10): controlled write round-trip on Pinceau's tag ONLY.

Run manually on the local host only, never in CI. Double-gated: requires
SUREPETCARE_LIVE_WRITE=1 in the real environment AND the configured tag
to be Pinceau's 2119787; otherwise it aborts BEFORE any network call.

Flow (contracts §6 verification on every write):
    capture P0/V0 -> PUT the opposite profile -> verify ->
    if not at 3: PUT back to 3 -> verify -> final assert profile == 3.
The test MUST end at a verified profile 3 (spec R8); if any leg fails
mid-flight it still attempts the return-to-3 leg before exiting.

Usage:
    SUREPETCARE_LIVE_WRITE=1 python3 tests/live/l2_round_trip.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

PINCEAU_TAG = 2119787


async def main() -> None:
    # Gates first — abort before any network traffic or login.
    if os.environ.get("SUREPETCARE_LIVE_WRITE") != "1":
        sys.exit("L2 ABORT: SUREPETCARE_LIVE_WRITE != 1 — refusing to run (no changes made)")
    env = common.load_env()
    tag_id = int(common.require(env, "SUREPETCARE_TAG_ID_PINCEAU"))
    if tag_id != PINCEAU_TAG:
        sys.exit(
            f"L2 ABORT: configured tag {tag_id} != {PINCEAU_TAG} "
            "(Pinceau only) — refusing to run (no changes made)"
        )

    api = common.load_api()
    session, client = common.build_client(api, env)
    flap_id = int(common.require(env, "SUREPETCARE_DEVICE_ID"))
    try:
        await client.login()
        devices = await client.get_devices()
        device, tag = common.find_tag(devices, flap_id, tag_id)
        if tag is None:
            sys.exit(f"L2 ABORT: tag {tag_id} not readable on flap {flap_id} (no changes made)")
        p0, v0 = tag["profile"], tag["version"]
        print(f"L2 pre-state  | profile={p0} version={v0}")

        opposite = 2 if p0 == 3 else 3
        final = tag
        try:
            verified1 = await client.set_tag_profile(
                flap_id, tag_id, opposite, expected_prior_version=v0
            )
            print(
                f"L2 leg 1 done | profile={verified1['profile']} version={verified1['version']}"
            )
            final = verified1
        except Exception as error:  # noqa: BLE001 — always attempt the return leg
            print(f"L2 leg 1 FAILED: {error}")

        if final.get("profile") != 3:
            prior = final.get("version", v0)
            verified2 = await client.set_tag_profile(
                flap_id, tag_id, 3, expected_prior_version=prior
            )
            print(
                f"L2 leg 2 done | profile={verified2['profile']} version={verified2['version']}"
            )
            final = verified2

        if final.get("profile") != 3:
            sys.exit(
                f"L2 FAIL: final verified profile is {final.get('profile')}, expected 3"
            )
        print(
            f"L2 OK | ends at verified profile 3 | tag={tag_id} "
            f"version={final['version']}"
        )
    finally:
        await session.close()


asyncio.run(main())