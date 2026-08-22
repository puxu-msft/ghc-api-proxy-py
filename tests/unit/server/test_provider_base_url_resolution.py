"""The API base URL comes from the subscription, or from a URL written by hand — and from nothing else.

Ruled 2026-08-22, after `--ghc-api-base-url` was found to have been writing a field that no longer existed: it set `base_url` through `model_copy`, which does not validate names, so an operator asking for the enterprise host got the individual one with nothing said. The two remaining routes to a base URL are asserted here, and so is the boundary between them — a config that names a URL must not be probed at all, because probing it would make the operator's own answer conditional on a network call succeeding.

The requests the probe makes are recorded rather than mocked away, because "did not probe" is the assertion in three of these tests and an empty list is only evidence if some other test in the same harness proves the list fills up.
"""

from pathlib import Path
from typing import Any

import httpx2
import pytest

from app.config.loading import GITHUB_TOKEN_VARIABLE
from app.config.schema import ProxyConfig
from app.model_provider import GithubCopilotProvider
from app.server.composition import build_chain, resolve_provider_base_urls

INDIVIDUAL = "https://api.githubcopilot.com"


def provider_base_url(chain: Any, name: str = "ghc") -> str:
    """The URL the provider was actually built with, not the one the config carries.

    The registry answers with the `ModelProvider` protocol, which has no `base_url` — only this implementation does, and reading it is the whole point: a config that resolved correctly and a URL that never reached the SDK client is the shape of the defect these tests exist for.
    """
    provider = chain.providers.get(name)
    assert isinstance(provider, GithubCopilotProvider)
    return provider.base_url


def config_with(api_base_url: str, token_file: Path) -> ProxyConfig:
    return ProxyConfig.model_validate(
        {
            "model_providers": {
                "ghc": {
                    "type": "github_copilot",
                    "api_base_url": api_base_url,
                    "github_token_file": str(token_file),
                }
            }
        }
    )


def probe_client(usage: dict[str, Any], seen: list[httpx2.Request]) -> httpx2.AsyncClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=usage)

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("plan", "expected"),
    [
        ("business", "https://api.business.githubcopilot.com"),
        ("enterprise", "https://api.enterprise.githubcopilot.com"),
        ("individual", INDIVIDUAL),
    ],
)
async def test_the_subscription_selects_the_host(
    plan: str,
    expected: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GITHUB_TOKEN_VARIABLE, "ghu_from_env")
    seen: list[httpx2.Request] = []
    http_client = probe_client({"copilot_plan": plan}, seen)
    config = config_with("", tmp_path / "absent-token")
    try:
        resolved = await resolve_provider_base_urls(config, http_client=http_client)
        # Asserted on the provider rather than only on the config, because the config being right and the URL never reaching the SDK client is the shape of the defect this replaces.
        chain = build_chain(resolved, http_client=http_client)
    finally:
        await http_client.aclose()

    assert resolved.model_providers["ghc"].api_base_url == expected
    assert [str(request.url) for request in seen] == [
        "https://api.github.com/copilot_internal/user"
    ]
    assert seen[0].headers["authorization"] == "token ghu_from_env"
    assert provider_base_url(chain) == expected


@pytest.mark.asyncio
async def test_a_hand_written_base_url_is_never_probed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GITHUB_TOKEN_VARIABLE, "ghu_from_env")
    seen: list[httpx2.Request] = []
    # A plan that would resolve somewhere else entirely, so a probe that ran would be visible in the result and not only in `seen`.
    http_client = probe_client({"copilot_plan": "enterprise"}, seen)
    config = config_with("https://ghes.example.test", tmp_path / "absent-token")
    try:
        resolved = await resolve_provider_base_urls(config, http_client=http_client)
    finally:
        await http_client.aclose()

    assert resolved.model_providers["ghc"].api_base_url == "https://ghes.example.test"
    assert seen == []


@pytest.mark.asyncio
async def test_absent_credentials_leave_the_base_url_unresolved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Starting without a token is how this chain has always started. The probe must not turn that into a startup failure."""
    monkeypatch.delenv(GITHUB_TOKEN_VARIABLE, raising=False)
    seen: list[httpx2.Request] = []
    http_client = probe_client({"copilot_plan": "enterprise"}, seen)
    config = config_with("", tmp_path / "absent-token")
    try:
        resolved = await resolve_provider_base_urls(config, http_client=http_client)
        chain = build_chain(resolved, http_client=http_client)
    finally:
        await http_client.aclose()

    assert resolved.model_providers["ghc"].api_base_url == ""
    assert seen == []
    assert provider_base_url(chain) == INDIVIDUAL


@pytest.mark.asyncio
async def test_an_unrecognised_plan_leaves_the_base_url_unresolved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GITHUB_TOKEN_VARIABLE, "ghu_from_env")
    seen: list[httpx2.Request] = []
    http_client = probe_client({"copilot_plan": "something_new"}, seen)
    config = config_with("", tmp_path / "absent-token")
    try:
        resolved = await resolve_provider_base_urls(config, http_client=http_client)
    finally:
        await http_client.aclose()

    assert resolved.model_providers["ghc"].api_base_url == ""
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_a_refused_probe_is_raised_rather_than_defaulted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A token that exists and an answer we could not read is a fault, not a vote for the individual host.

    Falling back here would send an enterprise account's traffic to `api.githubcopilot.com` and say nothing, which is the failure mode this whole change exists to remove.
    """
    monkeypatch.setenv(GITHUB_TOKEN_VARIABLE, "ghu_from_env")
    http_client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(lambda _: httpx2.Response(403, json={"message": "no"}))
    )
    config = config_with("", tmp_path / "absent-token")
    try:
        with pytest.raises(httpx2.HTTPStatusError):
            await resolve_provider_base_urls(config, http_client=http_client)
    finally:
        await http_client.aclose()
