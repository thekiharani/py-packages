"""Route-drift conformance check.

Introspects a live ``Sendstack`` instance - discovering every resource namespace
and method dynamically - and captures the (HTTP method, path) each one calls.
The captured set must equal the canonical contract in ``conformance-routes.json``
(byte-identical across the SendStack SDK packages). This fails loudly if a method
is added, removed, or re-pointed at the wrong verb/path.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import httpx

from sendstack import Sendstack

FIXTURE = Path(__file__).parent / "conformance-routes.json"
_SENTINEL = "__ID__"


def _expected_routes() -> set[tuple[str, str]]:
    data = json.loads(FIXTURE.read_text())
    return {(route["method"], route["path"]) for route in data["routes"]}


def _normalize(path: str) -> str:
    return "/".join("{id}" if segment == _SENTINEL else segment for segment in path.split("/"))


def _synthesize_args(fn) -> list[object]:
    """Build positional args for a resource method from its signature.

    Required params whose name looks like an identifier get a sentinel (it lands
    in the path); any other required param gets an empty payload.
    """

    args: list[object] = []
    for param in inspect.signature(fn).parameters.values():
        if param.name == "options":
            continue
        if param.default is not inspect.Parameter.empty:
            continue
        if param.kind in (
            inspect.Parameter.KEYWORD_ONLY,
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            continue
        lowered = param.name.lower()
        args.append(_SENTINEL if "id" in lowered or "recipient" in lowered else {})
    return args


def _discover_actual_routes() -> set[tuple[str, str]]:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True, "data": {}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = Sendstack("conformance-token", client=http)
    actual: set[tuple[str, str]] = set()
    try:
        # Resources are the client attributes that point back at the client.
        # Keying by id() collapses aliases (webhook_events / webhookEvents).
        resources = {
            id(value): value
            for value in vars(client).values()
            if getattr(value, "_client", None) is client
        }
        for resource in resources.values():
            for attr in dir(resource):
                if attr.startswith("_"):
                    continue
                fn = getattr(resource, attr)
                if not callable(fn):
                    continue
                # Skip camelCase aliases (e.g. sendBatch -> send_batch): a bound
                # alias reports the underlying function's name.
                if getattr(fn, "__name__", attr) != attr:
                    continue
                del calls[:]
                fn(*_synthesize_args(fn))
                request = calls[-1]
                actual.add((request.method, _normalize(request.url.path)))
    finally:
        http.close()
    return actual


def test_sdk_routes_match_contract() -> None:
    actual = _discover_actual_routes()
    expected = _expected_routes()
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    assert not missing, f"Contract routes not implemented by the SDK: {missing}"
    assert not extra, f"SDK exposes routes absent from the contract: {extra}"


def test_contract_has_no_duplicate_routes() -> None:
    data = json.loads(FIXTURE.read_text())
    pairs = [(route["method"], route["path"]) for route in data["routes"]]
    assert len(pairs) == len(set(pairs))
    assert len(pairs) == 60
