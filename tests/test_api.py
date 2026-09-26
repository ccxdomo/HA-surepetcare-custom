"""T1-T10 (contracts §10): SurePetcareApiClient behavior via scripted HTTP.

Runs without Home Assistant: api.py is standalone by contract, and the
transport is a scripted fake session (helpers.py).
"""

from __future__ import annotations

import asyncio

import pytest

from helpers import FakeResponse, FakeSession, device_payloads, make_token

EMAIL = "user@example.test"
PASSWORD = "s3cret-p4ssword-041"

LOGIN_OK = lambda token: FakeResponse(  # noqa: E731
    200, {"data": {"token": token, "user": {"id": 12345}}}
)


def make_client(api_module, session):
    return api_module.SurePetcareApiClient(
        email=EMAIL, password=PASSWORD, session=session, timeout=10
    )


async def no_sleep(_seconds: float) -> None:
    """Fast stand-in for the verification retry sleep."""


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    """Never actually sleep between verification attempts in tests."""
    monkeypatch.setattr(asyncio, "sleep", no_sleep)


# ---------------------------------------------------------------------- T1


async def test_t1_login_stores_token_headers_and_body(api_module):
    """Login body shape exact; the full §5 header set + X-Device-Id."""
    token = make_token(492)
    session = FakeSession()
    session.expect("POST", "/auth/login", LOGIN_OK(token))
    session.expect("GET", "/device", FakeResponse(200, {"data": []}))
    client = make_client(api_module, session)

    await client.login()
    assert client._token == token

    login_request = session.requests[0]
    assert login_request["method"] == "POST"
    assert login_request["url"].endswith("/auth/login")
    # Exact login body shape (contracts §5.1).
    assert login_request["json"] == {
        "email_address": EMAIL,
        "password": PASSWORD,
        "device_id": client.device_id,
    }
    headers = login_request["headers"]
    assert headers["Content-Type"] == "application/json"
    assert headers["Accept"] == "application/json, text/plain, */*"
    assert headers["Origin"] == "https://surepetcare.io"
    assert headers["Referer"] == "https://surepetcare.io/"
    assert headers["Accept-Language"] == "en-US,en-GB;q=0.9"
    assert headers["X-Requested-With"] == "com.sureflap.surepetcare"
    assert "User-Agent" in headers
    # X-Device-Id always matches the login device_id (research §2).
    assert headers["X-Device-Id"] == client.device_id
    # The login call itself carries no bearer token.
    assert "Authorization" not in headers

    # Authenticated call: bearer present, X-Device-Id unchanged, no body
    # content type on a GET.
    await client.get_devices()
    authed = session.requests[1]
    assert authed["headers"]["Authorization"] == f"Bearer {token}"
    assert authed["headers"]["X-Device-Id"] == client.device_id
    assert "Content-Type" not in authed["headers"]


# ---------------------------------------------------------------------- T2


async def test_t2_login_401_auth_error_no_secret_leak(api_module, caplog):
    session = FakeSession()
    session.expect(
        "POST", "/auth/login", FakeResponse(401, text=f"no account for {EMAIL}")
    )
    client = make_client(api_module, session)
    with caplog.at_level("DEBUG"):
        with pytest.raises(api_module.SurePetcareApiAuthError) as excinfo:
            await client.login()
    # The response excerpt is redacted: email never leaks.
    assert EMAIL not in str(excinfo.value)
    assert "[redacted]" in str(excinfo.value)
    assert EMAIL not in caplog.text
    assert PASSWORD not in caplog.text


async def test_t2_login_timeout_connection_error(api_module, caplog):
    session = FakeSession()
    session.expect("POST", "/auth/login", asyncio.TimeoutError())
    client = make_client(api_module, session)
    with caplog.at_level("DEBUG"):
        with pytest.raises(api_module.SurePetcareApiConnectionError):
            await client.login()
    assert EMAIL not in caplog.text
    assert PASSWORD not in caplog.text


async def test_t2_login_500_is_auth_error(api_module):
    """Any non-200 on login is an auth error (contracts §5.1)."""
    session = FakeSession()
    session.expect("POST", "/auth/login", FakeResponse(500, text="boom"))
    client = make_client(api_module, session)
    with pytest.raises(api_module.SurePetcareApiAuthError) as excinfo:
        await client.login()
    assert "500" in str(excinfo.value)


# ---------------------------------------------------------------------- T3


async def test_t3_live_length_token_accepted(api_module):
    """A 492-char token is accepted — regression vs surepy's stale 448 cap."""
    token = make_token(492)
    session = FakeSession()
    session.expect("POST", "/auth/login", LOGIN_OK(token))
    client = make_client(api_module, session)
    await client.login()
    assert client._token == token


async def test_t3_longer_token_also_accepted(api_module):
    """No upper bound: an 800-char printable token is accepted too."""
    token = make_token(800)
    session = FakeSession()
    session.expect("POST", "/auth/login", LOGIN_OK(token))
    client = make_client(api_module, session)
    await client.login()
    assert client._token == token


async def test_t3_short_token_rejected(api_module):
    session = FakeSession()
    session.expect("POST", "/auth/login", LOGIN_OK(make_token(100)))
    client = make_client(api_module, session)
    with pytest.raises(api_module.SurePetcareApiAuthError) as excinfo:
        await client.login()
    assert "usable token" in str(excinfo.value)


# ---------------------------------------------------------------------- T4


async def test_t4_get_devices_parses_data_list(api_module):
    session = FakeSession()
    token = make_token(492)
    session.expect("POST", "/auth/login", LOGIN_OK(token))
    session.expect(
        "GET", "/device", FakeResponse(200, {"data": device_payloads(2, 13)})
    )
    client = make_client(api_module, session)
    devices = await client.get_devices()
    assert isinstance(devices, list)
    assert [d["id"] for d in devices] == [1073725, 1307328, 906099]
    # Hub carries tags: [] (research §1) and is passed through untouched.
    assert devices[0]["tags"] == []
    # The login happened lazily before the GET (which carries the with[] query).
    assert session.requests[0]["url"].endswith("/auth/login")
    assert session.requests[1]["url"].startswith(
        "https://app.api.surehub.io/api/device?with[]="
    )


async def test_t4_get_devices_missing_list_raises(api_module):
    session = FakeSession()
    session.expect("POST", "/auth/login", LOGIN_OK(make_token(492)))
    session.expect("GET", "/device", FakeResponse(200, {"unexpected": True}))
    client = make_client(api_module, session)
    with pytest.raises(api_module.SurePetcareApiError):
        await client.get_devices()


# ---------------------------------------------------------------------- T5


async def test_t5_set_tag_profile_happy_path(api_module):
    """PUT body is exactly {"profile": N}; verification read confirms."""
    token = make_token(492)
    session = FakeSession()
    session.expect("POST", "/auth/login", LOGIN_OK(token))
    session.expect(
        "PUT",
        "/device/1307328/tag/2119787",
        FakeResponse(200, {"data": {"profile": 3}}),
    )
    session.expect(
        "GET", "/device", FakeResponse(200, {"data": device_payloads(3, 14)})
    )
    client = make_client(api_module, session)

    verified = await client.set_tag_profile(
        1307328, 2119787, 3, expected_prior_version=13
    )
    assert verified["profile"] == 3
    assert verified["version"] == 14

    put = session.requests[1]
    assert put["method"] == "PUT"
    assert put["url"].endswith("/device/1307328/tag/2119787")
    # Body is exactly the profile dict — nothing else (contracts §6 step 2).
    assert put["json"] == {"profile": 3}
    assert put["headers"]["Authorization"] == f"Bearer {token}"
    assert put["headers"]["X-Device-Id"] == client.device_id


# ---------------------------------------------------------------------- T6


async def test_t6_verify_retry_passes_on_second_attempt(api_module):
    """First verification GET is stale (old version) → second passes."""
    token = make_token(492)
    session = FakeSession()
    session.expect("POST", "/auth/login", LOGIN_OK(token))
    session.expect("PUT", "/device/1307328/tag/2119787", FakeResponse(200, {}))
    session.expect(
        "GET", "/device", FakeResponse(200, {"data": device_payloads(2, 13)})
    )
    session.expect(
        "GET", "/device", FakeResponse(200, {"data": device_payloads(3, 14)})
    )
    client = make_client(api_module, session)

    verified = await client.set_tag_profile(
        1307328, 2119787, 3, expected_prior_version=13
    )
    assert verified["profile"] == 3
    assert verified["version"] == 14
    gets = [r for r in session.requests if r["method"] == "GET"]
    assert len(gets) == 2


# ---------------------------------------------------------------------- T7


async def test_t7_verify_exhaustion_raises(api_module):
    """All stale verification reads → SurepetcareVerificationError."""
    token = make_token(492)
    session = FakeSession()
    session.expect("POST", "/auth/login", LOGIN_OK(token))
    session.expect("PUT", "/device/1307328/tag/2119787", FakeResponse(200, {}))
    for _ in range(api_module.VERIFY_ATTEMPTS):
        session.expect(
            "GET", "/device", FakeResponse(200, {"data": device_payloads(2, 13)})
        )
    client = make_client(api_module, session)

    with pytest.raises(api_module.SurepetcareVerificationError) as excinfo:
        await client.set_tag_profile(
            1307328, 2119787, 3, expected_prior_version=13
        )
    # The error names the device/tag and the last observed state.
    assert "2119787" in str(excinfo.value)
    assert "1307328" in str(excinfo.value)
    # 1 login + 1 PUT + N verification GETs — then stop, no extra traffic.
    assert len(session.requests) == 2 + api_module.VERIFY_ATTEMPTS


# ---------------------------------------------------------------------- T8


async def test_t8_put_401_relogin_once_and_retry(api_module):
    """PUT 401 → re-login once → PUT retried exactly once → verify."""
    token1, token2 = make_token(492), make_token(900)
    session = FakeSession()
    session.expect("POST", "/auth/login", LOGIN_OK(token1))
    session.expect(
        "PUT",
        "/device/1307328/tag/2119787",
        FakeResponse(401, text="token expired"),
    )
    session.expect("POST", "/auth/login", LOGIN_OK(token2))
    session.expect("PUT", "/device/1307328/tag/2119787", FakeResponse(200, {}))
    session.expect(
        "GET", "/device", FakeResponse(200, {"data": device_payloads(3, 14)})
    )
    client = make_client(api_module, session)

    verified = await client.set_tag_profile(
        1307328, 2119787, 3, expected_prior_version=13
    )
    assert verified["version"] == 14
    logins = [r for r in session.requests if r["url"].endswith("/auth/login")]
    puts = [r for r in session.requests if r["method"] == "PUT"]
    assert len(logins) == 2  # initial lazy login + exactly one re-login
    assert len(puts) == 2  # the failed PUT + exactly one retry
    # The retried PUT carries the fresh token.
    assert puts[1]["headers"]["Authorization"] == f"Bearer {token2}"


async def test_t8_relogin_failure_propagates_auth_error(api_module):
    session = FakeSession()
    session.expect("POST", "/auth/login", LOGIN_OK(make_token(492)))
    session.expect(
        "PUT",
        "/device/1307328/tag/2119787",
        FakeResponse(401, text="token expired"),
    )
    session.expect("POST", "/auth/login", FakeResponse(401, text="bad credentials"))
    client = make_client(api_module, session)
    with pytest.raises(api_module.SurePetcareApiAuthError):
        await client.set_tag_profile(
            1307328, 2119787, 3, expected_prior_version=13
        )
    # No retry PUT after the failed re-login.
    puts = [r for r in session.requests if r["method"] == "PUT"]
    assert len(puts) == 1


# ---------------------------------------------------------------------- T9


async def test_t9_verify_get_401_relogin_once_and_continue(api_module):
    """A 401 during the verification read follows the single-relogin rule."""
    token1, token2 = make_token(492), make_token(750)
    session = FakeSession()
    session.expect("POST", "/auth/login", LOGIN_OK(token1))
    session.expect("PUT", "/device/1307328/tag/2119787", FakeResponse(200, {}))
    session.expect("GET", "/device", FakeResponse(401, text="stale token"))
    session.expect("POST", "/auth/login", LOGIN_OK(token2))
    session.expect(
        "GET", "/device", FakeResponse(200, {"data": device_payloads(3, 14)})
    )
    client = make_client(api_module, session)

    verified = await client.set_tag_profile(
        1307328, 2119787, 3, expected_prior_version=13
    )
    assert verified["profile"] == 3
    assert verified["version"] == 14
    logins = [r for r in session.requests if r["url"].endswith("/auth/login")]
    assert len(logins) == 2


# --------------------------------------------------------------------- T10


@pytest.mark.parametrize("status", [400, 422, 500])
async def test_t10_put_non_2xx_raises_no_retry_no_verify(api_module, status):
    session = FakeSession()
    session.expect("POST", "/auth/login", LOGIN_OK(make_token(492)))
    session.expect(
        "PUT",
        "/device/1307328/tag/2119787",
        FakeResponse(status, text=f"rejected {PASSWORD}"),
    )
    client = make_client(api_module, session)

    with pytest.raises(api_module.SurePetcareApiError) as excinfo:
        await client.set_tag_profile(
            1307328, 2119787, 3, expected_prior_version=13
        )
    # The error names the HTTP status, never the password.
    assert str(status) in str(excinfo.value)
    assert PASSWORD not in str(excinfo.value)
    # No retry, no verification reads, no success.
    puts = [r for r in session.requests if r["method"] == "PUT"]
    gets = [r for r in session.requests if r["method"] == "GET"]
    assert len(puts) == 1
    assert gets == []


async def test_t10_concurrent_writer_version_jump_warns(api_module, caplog):
    """version > prior+1 still passes but logs a concurrent-writer warning."""
    token = make_token(492)
    session = FakeSession()
    session.expect("POST", "/auth/login", LOGIN_OK(token))
    session.expect("PUT", "/device/1307328/tag/2119787", FakeResponse(200, {}))
    session.expect(
        "GET", "/device", FakeResponse(200, {"data": device_payloads(3, 16)})
    )
    client = make_client(api_module, session)

    with caplog.at_level("DEBUG"):
        verified = await client.set_tag_profile(
            1307328, 2119787, 3, expected_prior_version=13
        )
    assert verified["version"] == 16  # +3: pass, but warned
    assert "concurrent writer" in caplog.text


async def test_t10_missing_tag_in_verification_keeps_retrying(api_module):
    """Device/tag not visible yet in /device → retry until exhaustion."""
    token = make_token(492)
    session = FakeSession()
    session.expect("POST", "/auth/login", LOGIN_OK(token))
    session.expect("PUT", "/device/1307328/tag/2119787", FakeResponse(200, {}))
    empty = [{"id": 1073725, "product_id": 1, "tags": []}]
    for _ in range(api_module.VERIFY_ATTEMPTS):
        session.expect("GET", "/device", FakeResponse(200, {"data": empty}))
    client = make_client(api_module, session)

    with pytest.raises(api_module.SurepetcareVerificationError):
        await client.set_tag_profile(
            1307328, 2119787, 3, expected_prior_version=13
        )
    assert len(session.requests) == 2 + api_module.VERIFY_ATTEMPTS