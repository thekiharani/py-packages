from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from noriapay import (
    ApiError,
    AuthenticationError,
    ConfigurationError,
    Hooks,
    NetworkError,
    RetryDecisionContext,
    RetryPolicy,
    TimeoutError,
)
from noriapay.http import (
    AsyncHttpClient,
    HttpClient,
    _build_request_kwargs,
    _calculate_retry_delay,
    _normalize_hook_sequence,
    _resolve_retry_policy,
    _should_retry,
)
from noriapay.oauth import AsyncClientCredentialsTokenProvider, ClientCredentialsTokenProvider
from noriapay.types import AccessToken, HttpRequestOptions
from noriapay.utils import (
    append_path,
    build_error_message,
    encode_basic_auth,
    merge_headers,
    normalize_headers,
    parse_response_body,
    to_amount_string,
    to_object,
)
from tests.support import (
    FakeAsyncClient,
    FakeSyncClient,
    make_json_response,
    make_network_error,
    make_text_response,
    make_timeout_error,
)


def test_utils_cover_non_json_and_helper_paths() -> None:
    assert append_path("https://api.example.com/", "v1/test") == "https://api.example.com/v1/test"
    assert append_path("https://api.example.com", "https://override.example.com/path") == (
        "https://override.example.com/path"
    )
    assert encode_basic_auth("user", "pass") == "dXNlcjpwYXNz"
    assert to_amount_string("1.00") == "1.00"
    assert to_amount_string(1) == "1"
    assert to_amount_string(1.50) == "1.5"

    assert parse_response_body(make_json_response(200, {"ok": True})) == {"ok": True}
    assert parse_response_body(
        make_text_response(
            200,
            '{"hello":"world"}',
            headers={"content-type": "text/plain"},
        )
    ) == {"hello": "world"}
    assert (
        parse_response_body(
            make_text_response(
                200,
                "raw text",
                headers={"content-type": "text/plain"},
            )
        )
        == "raw text"
    )
    assert (
        parse_response_body(make_text_response(200, "", headers={"content-type": "text/plain"}))
        is None
    )

    assert to_object({"ok": True}) == {"ok": True}
    assert to_object("nope") == {}
    assert build_error_message(400, {"errorMessage": "provider error"}) == "provider error"
    assert build_error_message(422, {"detail": "invalid"}) == "invalid"
    assert build_error_message(500, {"message": "broken"}) == "broken"
    assert build_error_message(418, {"missing": "message"}) == "Request failed with status 418"
    assert normalize_headers(None) == {}
    assert normalize_headers({"x-test": "1"}) == {"x-test": "1"}
    assert merge_headers({"a": "1"}, None, {"b": "2"}) == {"a": "1", "b": "2"}


def test_http_client_creates_default_client_normalizes_hooks_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = HttpClient(base_url="https://example.com")
    assert isinstance(client.client, httpx.Client)

    closed: list[str] = []
    monkeypatch.setattr(client.client, "close", lambda: closed.append("closed"))

    def hook(context: Any) -> None:
        return None

    assert _normalize_hook_sequence(None) == []
    assert _normalize_hook_sequence(hook) == [hook]
    assert _normalize_hook_sequence([hook]) == [hook]
    assert _calculate_retry_delay(None, 1) == 0.0

    with client as entered:
        assert entered is client

    assert closed == ["closed"]


def test_http_client_posts_text_and_runs_hooks() -> None:
    before_calls: list[str] = []
    after_bodies: list[object] = []

    def before_request(context: Any) -> None:
        before_calls.append(context.url)
        context.headers["x-hooked"] = "yes"

    def after_response(context: Any) -> None:
        after_bodies.append(context.response_body)

    sync_client = FakeSyncClient(responses=[make_text_response(200, "ok")])
    client = HttpClient(
        base_url="https://example.com",
        client=sync_client,
        default_headers={"x-default": "1"},
        hooks=Hooks(
            before_request=before_request,
            after_response=after_response,
        ),
    )

    response = client.request(HttpRequestOptions(path="/echo", method="POST", body="hello"))

    assert response == "ok"
    assert before_calls == ["https://example.com/echo"]
    assert after_bodies == ["ok"]
    assert sync_client.calls[0]["headers"]["x-default"] == "1"
    assert sync_client.calls[0]["headers"]["x-hooked"] == "yes"
    assert sync_client.calls[0]["headers"]["content-type"] == "text/plain;charset=UTF-8"
    assert sync_client.calls[0]["content"] == "hello"


def test_http_client_retries_and_wraps_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    timeout_errors: list[Exception] = []

    monkeypatch.setattr("noriapay.http.time.sleep", lambda seconds: sleeps.append(seconds))

    retrying_client = HttpClient(
        base_url="https://example.com",
        client=FakeSyncClient(
            responses=[
                make_timeout_error("https://example.com/timeout"),
                make_json_response(200, {"status": "ok"}),
            ]
        ),
        retry=RetryPolicy(
            max_attempts=2,
            retry_methods=("GET",),
            retry_on_network_error=True,
            base_delay_seconds=0.25,
        ),
        hooks=Hooks(on_error=lambda context: timeout_errors.append(context.error)),
    )

    assert retrying_client.request(HttpRequestOptions(path="/timeout", method="GET")) == {
        "status": "ok"
    }
    assert isinstance(timeout_errors[0], TimeoutError)
    assert sleeps == [0.25]

    network_retry_client = HttpClient(
        base_url="https://example.com",
        client=FakeSyncClient(
            responses=[
                make_network_error("https://example.com/network-retry"),
                make_json_response(200, {"status": "recovered"}),
            ]
        ),
        retry=RetryPolicy(
            max_attempts=2,
            retry_methods=("GET",),
            retry_on_network_error=True,
        ),
    )
    assert network_retry_client.request(
        HttpRequestOptions(path="/network-retry", method="GET")
    ) == {"status": "recovered"}

    failing_client = HttpClient(
        base_url="https://example.com",
        client=FakeSyncClient(responses=[make_network_error("https://example.com/network")]),
    )
    with pytest.raises(NetworkError):
        failing_client.request(HttpRequestOptions(path="/network", method="GET"))

    timeout_client = HttpClient(
        base_url="https://example.com",
        client=FakeSyncClient(responses=[make_timeout_error("https://example.com/timeout-once")]),
    )
    with pytest.raises(TimeoutError):
        timeout_client.request(HttpRequestOptions(path="/timeout-once", method="GET"))

    impossible_client = HttpClient(
        base_url="https://example.com",
        client=FakeSyncClient(responses=[]),
        retry=RetryPolicy(max_attempts=0),
    )
    with pytest.raises(RuntimeError, match="unreachable retry state"):
        impossible_client.request(HttpRequestOptions(path="/impossible", method="GET"))


def test_http_client_wraps_api_errors_and_helper_functions() -> None:
    on_error_payloads: list[object] = []
    client = HttpClient(
        base_url="https://example.com",
        client=FakeSyncClient(
            responses=[
                make_json_response(500, {"message": "try again"}),
                make_json_response(200, {"status": True}),
            ]
        ),
        retry=RetryPolicy(
            max_attempts=2,
            retry_methods=("GET",),
            retry_on_statuses=(500,),
            should_retry=lambda context: context.status == 500,
        ),
        hooks=Hooks(on_error=lambda context: on_error_payloads.append(context.response_body)),
    )

    assert client.request(HttpRequestOptions(path="/status", method="GET")) == {"status": True}
    assert on_error_payloads == [{"message": "try again"}]

    api_client = HttpClient(
        base_url="https://example.com",
        client=FakeSyncClient(responses=[make_json_response(400, {"message": "bad request"})]),
    )
    with pytest.raises(ApiError) as error:
        api_client.request(HttpRequestOptions(path="/bad", method="GET"))
    assert error.value.status_code == 400

    base_retry = RetryPolicy(
        max_attempts=4,
        retry_methods=("GET",),
        retry_on_statuses=(500,),
        retry_on_network_error=True,
    )
    override = RetryPolicy(max_attempts=3)
    merged = _resolve_retry_policy(base_retry, override)
    assert merged is not None
    assert merged.max_attempts == 3
    assert merged.retry_methods == ("GET",)
    assert merged.retry_on_statuses == (500,)
    assert _resolve_retry_policy(base_retry, False) is None
    assert _resolve_retry_policy(base_retry, None) == base_retry
    assert _resolve_retry_policy(None, override) == override
    assert not _should_retry(
        base_retry,
        RetryDecisionContext(
            attempt=1,
            max_attempts=2,
            method="POST",
            url="https://example.com",
            status=500,
        ),
    )
    assert not _should_retry(
        base_retry,
        RetryDecisionContext(
            attempt=1,
            max_attempts=2,
            method="GET",
            url="https://example.com",
            status=404,
        ),
    )
    assert not _should_retry(
        RetryPolicy(max_attempts=2, retry_methods=("GET",)),
        RetryDecisionContext(
            attempt=1,
            max_attempts=2,
            method="GET",
            url="https://example.com",
            error=NetworkError("network"),
        ),
    )
    request_kwargs = _build_request_kwargs(
        method="POST",
        url="https://example.com/path",
        headers={"x-test": "1"},
        query={"country": "kenya", "skip": None},
        body={"amount": 1},
        timeout_seconds=5.0,
    )
    assert request_kwargs["params"] == {"country": "kenya"}
    assert request_kwargs["json"] == {"amount": 1}
    assert request_kwargs["headers"]["content-type"] == "application/json"
    assert _calculate_retry_delay(RetryPolicy(base_delay_seconds=0.5), 2) == 1.0


def test_async_http_client_covers_success_retry_errors_and_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        client = AsyncHttpClient(base_url="https://example.com")
        assert isinstance(client.client, httpx.AsyncClient)

        closed: list[str] = []

        async def fake_close() -> None:
            closed.append("closed")

        monkeypatch.setattr(client.client, "aclose", fake_close)
        async with client as entered:
            assert entered is client
        assert closed == ["closed"]

        before_calls: list[str] = []
        after_bodies: list[object] = []

        def before_request(context: Any) -> None:
            before_calls.append(context.url)
            context.headers["x-hooked"] = "yes"

        def after_response(context: Any) -> None:
            after_bodies.append(context.response_body)

        async_client = AsyncHttpClient(
            base_url="https://example.com",
            client=FakeAsyncClient(responses=[make_text_response(200, "ok")]),
            default_headers={"x-default": "1"},
            hooks=Hooks(before_request=before_request, after_response=after_response),
        )
        response = await async_client.request(
            HttpRequestOptions(path="/echo", method="POST", body="hello")
        )
        assert response == "ok"
        fake_client = async_client.client
        assert before_calls == ["https://example.com/echo"]
        assert after_bodies == ["ok"]
        assert fake_client.calls[0]["headers"]["content-type"] == "text/plain;charset=UTF-8"
        assert fake_client.calls[0]["content"] == "hello"

        sleeps: list[float] = []
        timeout_errors: list[Exception] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        monkeypatch.setattr("noriapay.http.asyncio.sleep", fake_sleep)

        retrying_client = AsyncHttpClient(
            base_url="https://example.com",
            client=FakeAsyncClient(
                responses=[
                    make_timeout_error("https://example.com/timeout"),
                    make_json_response(200, {"status": "ok"}),
                ]
            ),
            retry=RetryPolicy(
                max_attempts=2,
                retry_methods=("GET",),
                retry_on_network_error=True,
                base_delay_seconds=0.25,
            ),
            hooks=Hooks(on_error=lambda context: timeout_errors.append(context.error)),
        )
        assert await retrying_client.request(HttpRequestOptions(path="/timeout", method="GET")) == {
            "status": "ok"
        }
        assert isinstance(timeout_errors[0], TimeoutError)
        assert sleeps == [0.25]

        network_retry_client = AsyncHttpClient(
            base_url="https://example.com",
            client=FakeAsyncClient(
                responses=[
                    make_network_error("https://example.com/network-retry"),
                    make_json_response(200, {"status": "recovered"}),
                ]
            ),
            retry=RetryPolicy(
                max_attempts=2,
                retry_methods=("GET",),
                retry_on_network_error=True,
            ),
        )
        assert await network_retry_client.request(
            HttpRequestOptions(path="/network-retry", method="GET")
        ) == {"status": "recovered"}

        failing_client = AsyncHttpClient(
            base_url="https://example.com",
            client=FakeAsyncClient(responses=[make_network_error("https://example.com/network")]),
        )
        with pytest.raises(NetworkError):
            await failing_client.request(HttpRequestOptions(path="/network", method="GET"))

        timeout_client = AsyncHttpClient(
            base_url="https://example.com",
            client=FakeAsyncClient(
                responses=[make_timeout_error("https://example.com/timeout-once")]
            ),
        )
        with pytest.raises(TimeoutError):
            await timeout_client.request(HttpRequestOptions(path="/timeout-once", method="GET"))

        api_client = AsyncHttpClient(
            base_url="https://example.com",
            client=FakeAsyncClient(responses=[make_json_response(400, {"message": "bad request"})]),
        )
        with pytest.raises(ApiError):
            await api_client.request(HttpRequestOptions(path="/bad", method="GET"))

        retrying_api_client = AsyncHttpClient(
            base_url="https://example.com",
            client=FakeAsyncClient(
                responses=[
                    make_json_response(500, {"message": "try again"}),
                    make_json_response(200, {"status": True}),
                ]
            ),
            retry=RetryPolicy(
                max_attempts=2,
                retry_methods=("GET",),
                retry_on_statuses=(500,),
                base_delay_seconds=0.25,
            ),
        )
        assert await retrying_api_client.request(
            HttpRequestOptions(path="/status-retry", method="GET")
        ) == {"status": True}

        impossible_client = AsyncHttpClient(
            base_url="https://example.com",
            client=FakeAsyncClient(responses=[]),
            retry=RetryPolicy(max_attempts=0),
        )
        with pytest.raises(RuntimeError, match="unreachable retry state"):
            await impossible_client.request(HttpRequestOptions(path="/impossible", method="GET"))

    asyncio.run(run())


def test_token_provider_caches_wraps_failures_and_supports_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_without_client = ClientCredentialsTokenProvider(
        token_url="https://example.com/token",
        client_id="client-id",
        client_secret="client-secret",
    )
    assert isinstance(provider_without_client.client, httpx.Client)

    closed: list[str] = []
    monkeypatch.setattr(provider_without_client.client, "close", lambda: closed.append("closed"))
    with provider_without_client as provider:
        assert provider is provider_without_client
    assert closed == ["closed"]

    sync_client = FakeSyncClient(
        responses=[
            make_json_response(200, {"access_token": "token-1", "expires_in": 3600}),
            make_json_response(200, {"access_token": "token-2", "expires_in": 3600}),
        ]
    )
    provider = ClientCredentialsTokenProvider(
        token_url="https://example.com/token",
        client_id="client-id",
        client_secret="client-secret",
        client=sync_client,
    )

    assert provider.get_access_token() == "token-1"
    assert provider.get_token().access_token == "token-1"
    assert len(sync_client.calls) == 1

    provider.clear_cache()
    assert provider.get_access_token() == "token-2"
    assert len(sync_client.calls) == 2

    mapped_provider = ClientCredentialsTokenProvider(
        token_url="https://example.com/token",
        client_id="client-id",
        client_secret="client-secret",
        client=FakeSyncClient(responses=[make_json_response(200, {"token": "mapped"})]),
        map_response=lambda payload: AccessToken(
            access_token=str(payload["token"]),
            expires_in=3600,
            raw=payload,
        ),
    )
    assert mapped_provider.get_access_token() == "mapped"

    with pytest.raises(ConfigurationError):
        ClientCredentialsTokenProvider(
            token_url="https://example.com/token",
            client_id="client-id",
            client_secret="client-secret",
            client=FakeSyncClient(responses=[]),
            session=FakeSyncClient(responses=[]),
        )

    timeout_provider = ClientCredentialsTokenProvider(
        token_url="https://example.com/token",
        client_id="client-id",
        client_secret="client-secret",
        client=FakeSyncClient(responses=[make_timeout_error("https://example.com/token")]),
    )
    with pytest.raises(AuthenticationError):
        timeout_provider.get_token()

    network_provider = ClientCredentialsTokenProvider(
        token_url="https://example.com/token",
        client_id="client-id",
        client_secret="client-secret",
        client=FakeSyncClient(responses=[make_network_error("https://example.com/token")]),
    )
    with pytest.raises(AuthenticationError):
        network_provider.get_token()

    bad_response_provider = ClientCredentialsTokenProvider(
        token_url="https://example.com/token",
        client_id="client-id",
        client_secret="client-secret",
        client=FakeSyncClient(
            responses=[
                httpx.Response(
                    401,
                    text="{invalid",
                    headers={"content-type": "application/json"},
                )
            ]
        ),
    )
    with pytest.raises(AuthenticationError):
        bad_response_provider.get_token()


def test_async_token_provider_caches_wraps_failures_and_supports_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        provider_without_client = AsyncClientCredentialsTokenProvider(
            token_url="https://example.com/token",
            client_id="client-id",
            client_secret="client-secret",
        )
        assert isinstance(provider_without_client.client, httpx.AsyncClient)

        closed: list[str] = []

        async def fake_close() -> None:
            closed.append("closed")

        monkeypatch.setattr(provider_without_client.client, "aclose", fake_close)
        async with provider_without_client as provider:
            assert provider is provider_without_client
        assert closed == ["closed"]

        async_client = FakeAsyncClient(
            responses=[
                make_json_response(200, {"access_token": "token-1", "expires_in": 3600}),
                make_json_response(200, {"access_token": "token-2", "expires_in": 3600}),
            ]
        )
        provider = AsyncClientCredentialsTokenProvider(
            token_url="https://example.com/token",
            client_id="client-id",
            client_secret="client-secret",
            client=async_client,
        )

        assert await provider.get_access_token() == "token-1"
        assert (await provider.get_token()).access_token == "token-1"
        assert len(async_client.calls) == 1

        provider.clear_cache()
        assert await provider.get_access_token() == "token-2"
        assert len(async_client.calls) == 2

        timeout_provider = AsyncClientCredentialsTokenProvider(
            token_url="https://example.com/token",
            client_id="client-id",
            client_secret="client-secret",
            client=FakeAsyncClient(responses=[make_timeout_error("https://example.com/token")]),
        )
        with pytest.raises(AuthenticationError):
            await timeout_provider.get_token()

        network_provider = AsyncClientCredentialsTokenProvider(
            token_url="https://example.com/token",
            client_id="client-id",
            client_secret="client-secret",
            client=FakeAsyncClient(responses=[make_network_error("https://example.com/token")]),
        )
        with pytest.raises(AuthenticationError):
            await network_provider.get_token()

        bad_response_provider = AsyncClientCredentialsTokenProvider(
            token_url="https://example.com/token",
            client_id="client-id",
            client_secret="client-secret",
            client=FakeAsyncClient(
                responses=[
                    httpx.Response(
                        401,
                        text="{invalid",
                        headers={"content-type": "application/json"},
                    )
                ]
            ),
        )
        with pytest.raises(AuthenticationError):
            await bad_response_provider.get_token()

    asyncio.run(run())
