"""Test doubles for the api.py unit tests (scripted HTTP transport)."""

from __future__ import annotations

from typing import Any

BASE_URL = "https://app.api.surehub.io/api"


class FakeResponse:
    """Minimal aiohttp response double used as an async context manager."""

    def __init__(self, status: int, payload: Any = None, text: str = "") -> None:
        self.status = status
        self._payload = payload
        self._text = text

    async def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no json payload scripted")
        return self._payload

    async def text(self) -> str:
        return self._text

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False


class FakeSession:
    """Scripted aiohttp session double: records requests, replays responses.

    Responses (or exceptions to raise) are consumed strictly in FIFO order and
    each one is asserted against the expected (method, path).
    """

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._script: list[tuple[tuple[str, str], Any]] = []

    def expect(self, method: str, path: str, response: Any) -> None:
        self._script.append(((method.upper(), path), response))

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.requests.append({"method": method.upper(), "url": url, **kwargs})
        if not self._script:
            raise AssertionError(
                f"unexpected HTTP request: {method} {url} (no scripted response left)"
            )
        (exp_method, exp_path), response = self._script.pop(0)
        path = url[len(BASE_URL):] if url.startswith(BASE_URL) else url
        if method.upper() != exp_method or not path.startswith(exp_path):
            raise AssertionError(
                f"unexpected HTTP request: {method} {url} "
                f"(expected {exp_method} {exp_path})"
            )
        if isinstance(response, Exception):
            raise response
        return response

    def urls(self) -> list[str]:
        return [request["url"] for request in self.requests]


def device_payloads(tag_profile: int, tag_version: int) -> list[dict[str, Any]]:
    """A /device data list with the fixture flap and hub (data-model §4)."""
    return [
        {
            "id": 200002,
            "product_id": 1,
            "name": "Hub Chatière",
            "household_id": 100241,
            "status": {"online": True},
            "tags": [],
        },
        {
            "id": 200001,
            "product_id": 6,
            "name": "la chatière ",
            "household_id": 100241,
            "status": {"online": True},
            "tags": [
                {
                    "id": 300001,
                    "device_id": 200001,
                    "index": 1,
                    "profile": 2,
                    "version": 3,
                },
                {
                    "id": 300002,
                    "device_id": 200001,
                    "index": 2,
                    "profile": 2,
                    "version": 9,
                },
                {
                    "id": 300003,
                    "device_id": 200001,
                    "index": 3,
                    "profile": tag_profile,
                    "version": tag_version,
                },
            ],
        },
        {
            "id": 200003,
            "product_id": 8,
            "name": "Felaqua",
            "household_id": 100241,
            "status": {"online": True},
            "tags": [
                {
                    "id": 300003,
                    "device_id": 200003,
                    "index": 3,
                    "profile": 2,
                    "version": 1,
                }
            ],
        },
    ]


def make_token(length: int = 492) -> str:
    """A printable-ASCII token of the given length (live tokens: 492 chars)."""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
    return (alphabet * (length // len(alphabet) + 1))[:length]