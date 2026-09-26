"""Minimal aiohttp client for the Sure Petcare write + verification path.

This module is deliberately standalone: aiohttp only, no Home Assistant and no
surepy imports, so it stays unit-testable outside HA (spec 041, contracts
§5). surepy 0.9.0 remains the read backbone; this client exists because surepy
swallows non-2xx statuses, retries a failed PUT as a GET on 401 and rejects
current 492-character tokens with a stale length cap (research.md §5).

It MUST NOT (contracts §5.2):
- log, return or expose the token, email or password anywhere,
- trust or parse the PUT response body as state,
- silently swallow non-2xx statuses,
- retry a failed PUT more than once,
- impose the surepy ``len(token) < 448`` cap.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Verified live (research.md §1).
BASE_URL = "https://app.api.surehub.io/api"
LOGIN_PATH = "/auth/login"
DEVICE_PATH = "/device?with[]=children&with[]=tags&with[]=control&with[]=status"

# surepy-style user agent, used by the live probes (research.md §2).
USER_AGENT = "surepy 0.9.0 - https://github.com/benleb/surepy"

# Mirrors of the contract constants (const.py carries the canonical copies for
# the HA-facing modules; these keep this module standalone-importable).
# 15 attempts x 5 s (~70 s window): live evidence 2026-09-26 showed /device
# reflects an accepted PUT only ~10 s later (see const.py for details).
VERIFY_ATTEMPTS = 15  # INDOOR_ONLY_VERIFY_ATTEMPTS
VERIFY_RETRY_SECONDS = 5  # INDOOR_ONLY_VERIFY_RETRY_SECONDS
MIN_TOKEN_LENGTH = 300  # no upper bound: live tokens are 492 chars (research §1)


class SurePetcareApiError(Exception):
    """Base error for the Sure Petcare write client."""


class SurePetcareApiAuthError(SurePetcareApiError):
    """Authentication with the Sure Petcare API failed."""


class SurePetcareApiConnectionError(SurePetcareApiError):
    """The Sure Petcare API could not be reached."""


class SurepetcareVerificationError(SurePetcareApiError):
    """The write could not be verified against the cloud after all attempts."""


class _UnauthorizedError(SurePetcareApiAuthError):
    """Internal marker: a 401 that qualifies for the single re-login retry."""


def _token_acceptable(token: Any) -> bool:
    """Accept any printable ASCII token of >= 300 chars (no stale upper cap)."""
    if not isinstance(token, str) or len(token) < MIN_TOKEN_LENGTH:
        return False
    return all(0x20 <= ord(character) <= 0x7E for character in token)


def _find_tag_assignment(
    devices: list[dict[str, Any]], device_id: int, tag_id: int
) -> dict[str, Any] | None:
    """Locate the (device, tag) assignment payload inside a /device list."""
    for device in devices:
        try:
            if int(device.get("id")) != int(device_id):
                continue
        except (TypeError, ValueError):
            continue
        for tag in device.get("tags") or []:
            try:
                if int(tag.get("id")) == int(tag_id):
                    return tag
            except (TypeError, ValueError):
                continue
    return None


class SurePetcareApiClient:
    """Client for login, the device read and the verified tag profile write."""

    def __init__(
        self,
        *,
        email: str,
        password: str,
        session: aiohttp.ClientSession,
        timeout: float,
    ) -> None:
        """Initialize with an injected aiohttp session (lazy login)."""
        self._email = email
        self._password = password
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        # In-memory session: fresh uuid4 per HA start (research §4, decision D5).
        self.device_id = str(uuid.uuid4())
        self._token: str | None = None

    def _headers(self, *, authenticated: bool, has_body: bool) -> dict[str, str]:
        """Build the required header set for every request (research §2)."""
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://surepetcare.io",
            "Referer": "https://surepetcare.io/",
            "Accept-Language": "en-US,en-GB;q=0.9",
            "X-Requested-With": "com.sureflap.surepetcare",
            "User-Agent": USER_AGENT,
            # Sent on every call (not an auth boundary, research §4) and always
            # matching the login body's device_id.
            "X-Device-Id": self.device_id,
        }
        if has_body:
            headers["Content-Type"] = "application/json"
        if authenticated:
            if not self._token:
                raise SurePetcareApiAuthError("no token available")
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _redact(self, text: str) -> str:
        """Strip credential material from error excerpts before logging them."""
        redacted = text
        for secret in (self._email, self._password, self._token):
            if secret and secret in redacted:
                redacted = redacted.replace(secret, "[redacted]")
        return redacted[:200]

    async def _raw_request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        """Perform exactly one HTTP attempt and map failures to the taxonomy."""
        try:
            async with self._session.request(
                method,
                BASE_URL + path,
                json=json_body,
                headers=self._headers(
                    authenticated=authenticated, has_body=json_body is not None
                ),
                timeout=self._timeout,
            ) as response:
                status = response.status
                if 200 <= status < 300:
                    try:
                        return await response.json()
                    except (aiohttp.ContentTypeError, ValueError) as error:
                        raise SurePetcareApiError(
                            f"Sure Petcare API returned invalid JSON for {method} {path}: HTTP {status}"
                        ) from error
                excerpt = self._redact(await response.text())
                if status == 401 and authenticated:
                    raise _UnauthorizedError(
                        "Sure Petcare API rejected the access token: HTTP 401"
                    )
                if not authenticated:
                    raise SurePetcareApiAuthError(
                        f"Sure Petcare login failed: HTTP {status}: {excerpt}"
                    )
                raise SurePetcareApiError(
                    f"Sure Petcare API error: {method} {path} failed with HTTP {status}: {excerpt}"
                )
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            raise SurePetcareApiConnectionError(
                f"Could not reach the Sure Petcare API for {method} {path}"
            ) from error

    async def login(self) -> None:
        """Log in and store the session token (contracts §5.1)."""
        body = {
            "email_address": self._email,
            "password": self._password,
            "device_id": self.device_id,
        }
        data = await self._raw_request(
            "POST", LOGIN_PATH, json_body=body, authenticated=False
        )
        token = data.get("data", {}).get("token") if isinstance(data, dict) else None
        if not _token_acceptable(token):
            raise SurePetcareApiAuthError(
                "Sure Petcare login response did not contain a usable token"
            )
        self._token = token

    async def _request(
        self, method: str, path: str, *, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Lazy login plus the single-relogin retry wrapper (contracts §5.1).

        A 401 clears the token, logs in exactly once and retries the failed
        call exactly once. A second failure propagates as an auth error.
        """
        if self._token is None:
            await self.login()
        try:
            return await self._raw_request(
                method, path, json_body=json_body, authenticated=True
            )
        except _UnauthorizedError:
            _LOGGER.debug(
                "401 from Sure Petcare API; re-logging in once and retrying %s %s",
                method,
                path,
            )
            self._token = None
            await self.login()
            return await self._raw_request(
                method, path, json_body=json_body, authenticated=True
            )

    async def get_devices(self) -> list[dict[str, Any]]:
        """Read all devices with children/tags/control/status (fresh read)."""
        data = await self._request("GET", DEVICE_PATH)
        devices = data.get("data") if isinstance(data, dict) else None
        if not isinstance(devices, list):
            raise SurePetcareApiError(
                "Sure Petcare /device response did not contain a device list"
            )
        return devices

    async def set_tag_profile(
        self,
        device_id: int,
        tag_id: int,
        profile: int,
        *,
        expected_prior_version: int,
    ) -> dict[str, Any]:
        """PUT the tag profile, then verify it on /device (contracts §6).

        Never trusts the PUT response body: acceptance is proven only by a
        follow-up read showing the requested profile AND a version increment.
        """
        path = f"/device/{device_id}/tag/{tag_id}"
        await self._request("PUT", path, json_body={"profile": profile})

        last_observed: dict[str, Any] | None = None
        for attempt in range(1, VERIFY_ATTEMPTS + 1):
            if attempt > 1:
                await asyncio.sleep(VERIFY_RETRY_SECONDS)
            # A 401 here follows the single-relogin rule inside get_devices(),
            # then the loop continues (contracts §6 step 3a).
            devices = await self.get_devices()
            tag = _find_tag_assignment(devices, device_id, tag_id)
            if tag is None:
                _LOGGER.debug(
                    "verification attempt %s/%s: tag %s not yet visible on device %s",
                    attempt,
                    VERIFY_ATTEMPTS,
                    tag_id,
                    device_id,
                )
                continue
            last_observed = tag
            version = tag.get("version")
            if (
                tag.get("profile") == profile
                and isinstance(version, int)
                and version > expected_prior_version
            ):
                if version > expected_prior_version + 1:
                    _LOGGER.warning(
                        "concurrent writer detected: tag %s on device %s version %s jumped by more than 1 (expected prior %s)",
                        tag_id,
                        device_id,
                        version,
                        expected_prior_version,
                    )
                return tag
            _LOGGER.debug(
                "verification attempt %s/%s: profile=%s version=%s (waiting for profile %s with version greater than %s)",
                attempt,
                VERIFY_ATTEMPTS,
                tag.get("profile"),
                version,
                profile,
                expected_prior_version,
            )
        raise SurepetcareVerificationError(
            f"Could not verify the indoor-only change for tag {tag_id} on device {device_id} "
            f"after {VERIFY_ATTEMPTS} attempts: expected profile {profile} with version greater "
            f"than {expected_prior_version}; last observed profile="
            f"{last_observed.get('profile') if last_observed else 'unknown'} version="
            f"{last_observed.get('version') if last_observed else 'unknown'}"
        )