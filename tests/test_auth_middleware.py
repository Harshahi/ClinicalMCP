from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from mcp_clinical import server as server_module

TOKEN = "correct-horse-battery-staple"


def _ok(request):  # noqa: ANN001, ARG001 - Starlette endpoint signature
    return PlainTextResponse("ok")


def _build_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    pat: str = TOKEN,
    allowed_origins: frozenset[str] = frozenset(),
    allow_unauthenticated: bool = False,
) -> TestClient:
    monkeypatch.setattr(server_module, "MCP_PAT", pat)
    monkeypatch.setattr(server_module, "MCP_ALLOWED_ORIGINS", allowed_origins)
    monkeypatch.setattr(server_module, "MCP_ALLOW_UNAUTHENTICATED", allow_unauthenticated)

    inner = Starlette(routes=[Route("/mcp", _ok), Route("/some/new/route", _ok)])
    return TestClient(server_module.RequirePatMiddleware(inner))


def test_valid_token_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_client(monkeypatch)
    response = client.get("/mcp", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-token"},
        {"Authorization": f"Basic {TOKEN}"},
        {"Authorization": TOKEN},
        {"Authorization": "Bearer "},
    ],
)
def test_bad_or_missing_credentials_are_rejected(
    monkeypatch: pytest.MonkeyPatch, headers: dict[str, str]
) -> None:
    client = _build_client(monkeypatch)
    assert client.get("/mcp", headers=headers).status_code == 401


def test_auth_is_required_on_paths_other_than_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gate is fail-closed: a newly added route must not be public by default."""
    client = _build_client(monkeypatch)
    assert client.get("/some/new/route").status_code == 401
    assert (
        client.get("/some/new/route", headers={"Authorization": f"Bearer {TOKEN}"}).status_code
        == 200
    )


def test_missing_pat_refuses_to_serve(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_client(monkeypatch, pat="")
    response = client.get("/mcp")
    assert response.status_code == 503
    assert "misconfigured" in response.json()["error"]["message"].lower()


def test_missing_pat_serves_only_with_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_client(monkeypatch, pat="", allow_unauthenticated=True)
    assert client.get("/mcp").status_code == 200


def test_unlisted_origin_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_client(monkeypatch)
    response = client.get(
        "/mcp",
        headers={"Authorization": f"Bearer {TOKEN}", "Origin": "https://evil.example.com"},
    )
    assert response.status_code == 403


def test_listed_origin_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_client(
        monkeypatch, allowed_origins=frozenset({"https://app.example.com"})
    )
    response = client.get(
        "/mcp",
        headers={"Authorization": f"Bearer {TOKEN}", "Origin": "https://app.example.com"},
    )
    assert response.status_code == 200


def test_origin_check_runs_before_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """A rebinding attempt should be refused even without a token."""
    client = _build_client(monkeypatch)
    response = client.get("/mcp", headers={"Origin": "https://evil.example.com"})
    assert response.status_code == 403
