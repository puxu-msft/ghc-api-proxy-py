"""Path expansion and the token file it feeds.

The spec writes locations as `$XDG_DATA_HOME/ghc-api-proxy/...`, unset on a default Linux install.
Expanding it with `os.path.expandvars` alone would leave a literal `$XDG_DATA_HOME` directory name.
A token would then be looked for somewhere nobody wrote it.
"""

from pathlib import Path

import httpx2
import pytest

from app.config.paths import (
    PACKAGE_DIR_VARIABLE,
    expand_user_path,
    package_dir,
    standalone_pidfile_path,
    user_data_path,
)
from app.config.schema import ProxyConfig
from app.model_provider.ghc.auth.providers import FileTokenProvider
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


def test_a_fallback_carries_a_path_the_variable_does_not_yet_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`${VAR:-fallback}` is a shell form, and `os.path.expandvars` is not a shell.

    It reads `VAR:-fallback` as one variable name, finds no such variable, and leaves the
    token in the path — producing a directory literally named `${GHC_MODEL_INFO:-/tmp}`.
    A configured file would then be missing at a location nobody wrote and nothing would
    name the spelling that caused it.
    """
    monkeypatch.delenv("MODEL_INFO_HOME", raising=False)
    assert expand_user_path("${MODEL_INFO_HOME:-/srv/models}/opencode-go.json") == Path(
        "/srv/models/opencode-go.json"
    )


def test_a_set_variable_wins_over_its_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_INFO_HOME", "/from/env")
    assert expand_user_path("${MODEL_INFO_HOME:-/srv/models}/opencode-go.json") == Path(
        "/from/env/opencode-go.json"
    )


def test_an_empty_variable_takes_the_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    # `:-` rather than `-`: an exported but empty variable is the common shape of "nobody set this".
    monkeypatch.setenv("MODEL_INFO_HOME", "")
    assert expand_user_path("${MODEL_INFO_HOME:-/srv/models}/opencode-go.json") == Path(
        "/srv/models/opencode-go.json"
    )


def test_a_fallback_may_be_home_relative(monkeypatch: pytest.MonkeyPatch) -> None:
    # `expanduser` only looks at the front of the string, and this fallback is not at the front.
    monkeypatch.delenv("MODEL_INFO_HOME", raising=False)
    assert expand_user_path("${MODEL_INFO_HOME:-~/models}/opencode-go.json") == (
        Path.home() / "models/opencode-go.json"
    )


def test_a_variable_without_a_fallback_keeps_the_expandvars_behaviour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Only the fallback form is new here. An unset plain `${VAR}` still surfaces as written instead of quietly collapsing to the root.
    monkeypatch.delenv("MODEL_INFO_HOME", raising=False)
    assert "${MODEL_INFO_HOME}" in str(expand_user_path("${MODEL_INFO_HOME}/x.json"))


def test_the_package_dir_names_the_installed_package_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`${GHC_PACKAGE_DIR}` is resolved from the install, not the environment.

    A uvx run has no checkout, so `contrib/` does not exist for it — while a file
    inside the package ships in the wheel, and the variable lets a config point at it
    without copying it somewhere first.
    """
    monkeypatch.delenv(PACKAGE_DIR_VARIABLE, raising=False)
    monkeypatch.setenv("HOME", "/nowhere")

    resolved = expand_user_path(
        "${" + PACKAGE_DIR_VARIABLE + "}/model_provider/opencode-go-20260916.json"
    )

    assert resolved == package_dir() / "model_provider" / "opencode-go-20260916.json"
    assert resolved.is_file()


def test_the_package_dir_plain_spelling_resolves_the_same_way() -> None:
    assert expand_user_path(
        f"${PACKAGE_DIR_VARIABLE}/model_provider/opencode-go-20260916.json"
    ) == expand_user_path(
        "${" + PACKAGE_DIR_VARIABLE + "}/model_provider/opencode-go-20260916.json"
    )


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


def test_an_unset_token_file_gets_a_default_named_after_its_provider() -> None:
    """One file per provider, ruled by the user 2026-08-28 alongside making the provider a required argument.

    Two providers that authenticate against different tenants hold two different GitHub tokens. A single shared `github_token` meant whichever logged in last silently became the credential for both — and `build_github_token_source` reads through this same function, so the file a login writes and the file the service opens stay one decision.
    """
    config = ProxyConfig.model_validate({"model_providers": {"ghc": {"type": "github_copilot"}}})
    assert github_token_path(config, "ghc") == user_data_path() / "github_token-ghc.txt"


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


def test_an_unknown_provider_name_still_answers_rather_than_raising() -> None:
    # Named but not configured: the CLI refuses that before it gets here, so the answer only has to be defined, not useful.
    assert github_token_path(ProxyConfig(), "absent") == user_data_path() / "github_token-absent.txt"


def test_naming_no_provider_at_all_leaves_the_file_provider_its_own_default() -> None:
    # Nobody on the serving or CLI paths does this; the default argument still has to mean something.
    assert github_token_path(ProxyConfig()) is None


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


def test_the_pidfile_is_named_after_the_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", "/custom/data")
    assert standalone_pidfile_path(4141) == Path("/custom/data/ghc-api-proxy/standalone-4141.pid")


def test_a_named_directory_holds_the_same_port_derived_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The operator chooses the directory; the name inside it is not theirs to choose.

    A successor has to derive the file from nothing but the port it is taking over, so letting the setting name the file would break the one thing the file exists for.
    """
    monkeypatch.setenv("XDG_DATA_HOME", "/custom/data")
    assert standalone_pidfile_path(4141, Path("/run/ghc-api-proxy")) == Path(
        "/run/ghc-api-proxy/standalone-4141.pid"
    )


def test_two_ports_do_not_share_one_pidfile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Why the port is in the name at all.

    Under one shared name a throwaway `start` on another port claimed the same record: it overwrote the incumbent's entry on its way up and deleted it on its way down, leaving a process that was still serving but that no later `--restart` could find.
    """
    monkeypatch.setenv("XDG_DATA_HOME", "/custom/data")
    assert standalone_pidfile_path(4141) != standalone_pidfile_path(41411)
    # And a chosen directory does not collapse them either.
    named = Path("/run/ghc-api-proxy")
    assert standalone_pidfile_path(4141, named) != standalone_pidfile_path(41411, named)
