"""Path expansion and the token file it feeds.

The spec writes locations as `$XDG_DATA_HOME/ghc-api-proxy/...`, unset on a default Linux install.
Expanding it with `os.path.expandvars` alone would leave a literal `$XDG_DATA_HOME` directory name.
A token would then be looked for somewhere nobody wrote it.
"""

from pathlib import Path

import httpx2
import pytest

from app.config.paths import expand_user_path, user_data_path
from app.config.schema import ProxyConfig
from app.ghc_client.auth.providers import FileTokenProvider
from app.server.composition import build_chain, github_token_path

SPEC_TOKEN_PATH = "$XDG_DATA_HOME/ghc-api-proxy/github_token.txt"


def test_the_spec_spelling_resolves_when_the_variable_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    resolved = expand_user_path(SPEC_TOKEN_PATH)
    assert resolved == user_data_path() / "github_token.txt"
    assert "XDG_DATA_HOME" not in str(resolved)


def test_an_explicit_variable_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", "/custom/data")
    assert expand_user_path(SPEC_TOKEN_PATH) == Path("/custom/data/ghc-api-proxy/github_token.txt")


def test_braced_spelling_resolves_the_same_way(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    braced = "${XDG_DATA_HOME}/ghc-api-proxy/github_token.txt"
    assert expand_user_path(braced) == expand_user_path(SPEC_TOKEN_PATH)


def test_a_plain_absolute_path_is_left_alone() -> None:
    assert expand_user_path("/etc/ghc/token") == Path("/etc/ghc/token")


def test_a_home_relative_path_expands() -> None:
    assert expand_user_path("~/token") == Path.home() / "token"


def test_the_configured_token_file_reaches_the_file_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    config = ProxyConfig.model_validate(
        {
            "model_providers": {
                "ghc": {"type": "github_copilot", "github_token_file": SPEC_TOKEN_PATH}
            }
        }
    )
    assert github_token_path(config, "ghc") == user_data_path() / "github_token.txt"


def test_an_unset_token_file_defers_to_the_default_location() -> None:
    config = ProxyConfig.model_validate({"model_providers": {"ghc": {"type": "github_copilot"}}})
    # None, not a guessed path: the file provider owns its own default.
    assert github_token_path(config, "ghc") is None


def test_each_provider_gets_its_own_token_file() -> None:
    config = ProxyConfig.model_validate(
        {
            "model_providers": {
                "one": {"type": "github_copilot", "github_token_file": "/tokens/one"},
                "two": {"type": "github_copilot", "github_token_file": "/tokens/two"},
            }
        }
    )
    assert github_token_path(config, "one") == Path("/tokens/one")
    assert github_token_path(config, "two") == Path("/tokens/two")


def test_an_unknown_provider_name_falls_back_rather_than_raising() -> None:
    assert github_token_path(ProxyConfig(), "absent") is None


def test_build_chain_gives_each_provider_its_own_token_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The path decision must actually reach the file provider, per provider.

    Testing `github_token_path` alone leaves the call site free to drop the provider name.
    Every provider would then silently share one file.
    """
    seen: list[Path | None] = []

    class RecordingFileProvider(FileTokenProvider):
        def __init__(self, token_path: Path | None = None) -> None:
            seen.append(token_path)
            super().__init__(token_path)

    monkeypatch.setattr("app.server.composition.FileTokenProvider", RecordingFileProvider)
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "one",
            "model_providers": {
                "one": {"type": "github_copilot", "github_token_file": "/tokens/one"},
                "two": {"type": "github_copilot", "github_token_file": "/tokens/two"},
            },
        }
    )
    # Constructing the chain opens no connection, so the client needs no teardown here.
    build_chain(config, http_client=httpx2.AsyncClient())
    assert seen == [Path("/tokens/one"), Path("/tokens/two")]
