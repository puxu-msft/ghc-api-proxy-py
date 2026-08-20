"""What `debug models` reports, and what it does when it cannot report it.

The projection is tested against a hand-built payload for the cases that matter and against `refs/available_models.json` — a real capture of the catalog — for the shape. The hand-built one names conditions the capture does not happen to contain; the capture is what proves the reader survives the parts of a real entry nobody wrote a case for.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import typer.rich_utils
from rich.cells import cell_len
from typer.testing import CliRunner

from app.cli import app
from app.config.schema import ProxyConfig
from app.debug.models import (
    CatalogFailure,
    ProviderCatalog,
    build_rows,
    collect_catalogs,
    describe_failure,
    render_json,
    render_text,
)
from app.model_provider import GithubCopilotProvider, ProviderNotConfigured

runner = CliRunner()

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def plain_error_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    """Render Typer's own errors as plain, wide text for this file's assertions.

    Left alone, a usage error is styled and folded at 80 columns, which splits the list of configured provider names the message exists to deliver.
    """
    monkeypatch.setattr(typer.rich_utils, "COLOR_SYSTEM", None)
    monkeypatch.setattr(typer.rich_utils, "FORCE_TERMINAL", False)
    monkeypatch.setattr(typer.rich_utils, "MAX_WIDTH", 200)


def _model(model_id: str, **overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": model_id,
        "vendor": "Anthropic",
        "capabilities": {
            "family": model_id,
            "limits": {"max_context_window_tokens": 200000, "max_output_tokens": 64000},
        },
        "supported_endpoints": ["/v1/messages"],
    }
    entry.update(overrides)
    return entry


CATALOG: dict[str, Any] = {
    "object": "list",
    "data": [
        _model("routable"),
        _model("blocked"),
        _model("gated", policy={"state": "unconfigured"}),
        _model("silent", supported_endpoints=None),
        _model("ws-only", supported_endpoints=["ws:/responses"]),
        _model("half-driven", supported_endpoints=["/responses", "ws:/responses", "/telepathy"]),
    ],
}


def _rows_by_id(raw: dict[str, Any], *, disabled: list[str] | None = None):
    rows, _ = build_rows(raw, disabled=disabled or [])
    return {row.id: row for row in rows}


def test_status_names_what_stands_between_a_request_and_the_model() -> None:
    """Each blocked model is blocked for a different reason with a different fix.

    `silent` and `ws-only` are both unroutable and are deliberately not given the same word: one is upstream publishing no endpoints, the other is an endpoint we have chosen not to drive.
    """
    rows = _rows_by_id(CATALOG, disabled=["blocked"])

    assert rows["routable"].status == "ok"
    assert rows["blocked"].status == "disabled"
    assert rows["gated"].status == "policy:unconfigured"
    assert rows["silent"].status == "no-endpoints"
    assert rows["ws-only"].status == "no-driver"
    # One drivable endpoint is enough to route to, whatever else it also advertises.
    assert rows["half-driven"].status == "ok"


def test_an_upstream_policy_state_cannot_impersonate_one_of_our_own_words() -> None:
    """`policy.state` is chosen upstream. Reported bare, a state spelled `ok` says the model is routable when it is gated, and one spelled `disabled` is indistinguishable from the operator's own list."""
    rows = _rows_by_id(
        {
            "data": [
                _model("says-ok", policy={"state": "ok"}),
                _model("says-disabled", policy={"state": "disabled"}),
            ]
        }
    )

    assert rows["says-ok"].status == "policy:ok"
    assert rows["says-disabled"].status == "policy:disabled"
    # And neither is confusable with the local answers that carry different fixes.
    assert rows["says-ok"].status != "ok"
    assert rows["says-disabled"].status != "disabled"


def test_undriven_endpoints_are_kept_and_marked_apart() -> None:
    row = _rows_by_id(CATALOG)["half-driven"]

    # Nothing is dropped: an endpoint we have no name for is the one most worth seeing.
    assert row.endpoints == ("/responses", "/telepathy", "ws:/responses")
    assert row.undriven == frozenset({"/telepathy", "ws:/responses"})


def test_a_model_that_stated_no_limits_is_not_reported_as_zero() -> None:
    rows = _rows_by_id(
        {"data": [_model("quiet", capabilities={"family": "quiet", "limits": {}})]},
    )

    assert rows["quiet"].context_window is None
    assert rows["quiet"].max_output_tokens is None


def test_unreadable_entries_do_not_take_the_readable_ones_with_them() -> None:
    """This command exists to show a catalog nobody here controls; it must not be what fails when that catalog grows a shape we have not seen."""
    raw: dict[str, Any] = {
        "data": [
            "not-an-object",
            {"no": "id"},
            {"id": ""},
            {"id": "odd", "capabilities": {"limits": {"max_output_tokens": True}}},
            _model("fine"),
        ]
    }

    rows = _rows_by_id(raw)

    assert set(rows) == {"odd", "fine"}
    # `True` is an `int` in Python and is not a token count.
    assert rows["odd"].max_output_tokens is None


def test_entries_that_yield_no_row_are_counted_rather_than_dropped() -> None:
    """Four of these six produce no row. A report that says "2 models" and nothing else is indistinguishable from a catalog that really held two."""
    raw: dict[str, Any] = {
        "data": ["not-an-object", None, 42, {"no": "id"}, _model("fine"), _model("also-fine")],
    }

    rows, unreadable = build_rows(raw)

    assert len(rows) == 2
    assert unreadable == 4


def test_a_field_that_arrived_wrong_typed_is_not_answered_as_if_it_were_read() -> None:
    """`supported_endpoints` as a string used to report `no-endpoints` — a confident claim about upstream's offering made from a field nothing could read."""
    rows = _rows_by_id(
        {
            "data": [
                _model("string-endpoints", supported_endpoints="/responses"),
                _model("nonstr-policy", policy={"state": {"unexpected": True}}),
                _model("policy-not-an-object", policy="enabled"),
            ]
        }
    )

    assert rows["string-endpoints"].status == "malformed"
    assert rows["nonstr-policy"].status == "malformed"
    assert rows["policy-not-an-object"].status == "malformed"


def test_an_absent_optional_field_is_not_treated_as_malformed() -> None:
    """The negative control. 18 of the 42 models upstream served on 2026-08-20 legitimately omit `supported_endpoints`; calling those malformed would bury the real thing."""
    rows = _rows_by_id({"data": [_model("silent", supported_endpoints=None), _model("routable")]})

    assert rows["silent"].status == "no-endpoints"
    assert rows["routable"].status == "ok"


def test_a_payload_without_a_model_list_yields_no_rows() -> None:
    assert build_rows({"object": "list"}) == ((), 0)


def test_the_recorded_catalog_capture_reads_end_to_end() -> None:
    """Every entry of a real capture produces a row, and the fields are read from where they actually live.

    The hand-built payload above encodes what we believe an entry looks like. This one is what upstream actually sent, so it is the only place that catches a reader looking up `family` or the limits at the wrong depth — the shape of a row would stay valid while every value in it was empty.
    """
    raw = json.loads((REPO_ROOT / "refs" / "available_models.json").read_text(encoding="utf-8"))

    rows, unreadable = build_rows(raw, disabled=["gpt-4o"])
    by_id = {row.id: row for row in rows}

    assert len(rows) == len(raw["data"])
    assert unreadable == 0
    assert {row.id for row in rows if row.status == "disabled"} == {"gpt-4o"}
    assert not [row.id for row in rows if row.status == "malformed"]

    opus = by_id["claude-opus-4.6"]
    assert opus.status == "ok"
    assert opus.vendor == "Anthropic"
    assert opus.family == "claude-opus-4.6"
    assert opus.context_window == 1000000
    assert opus.max_output_tokens == 64000
    assert opus.endpoints == ("/chat/completions", "/v1/messages")
    assert opus.undriven == frozenset()


def _catalog(**overrides: Any) -> ProviderCatalog:
    raw = overrides.pop("raw", CATALOG)
    rows, unreadable = build_rows(raw, disabled=overrides.pop("disabled", ["blocked"]))
    return ProviderCatalog(
        name=overrides.pop("name", "ghc"),
        base_url=overrides.pop("base_url", "https://api.githubcopilot.com"),
        raw=raw,
        rows=rows,
        unreadable=unreadable,
    )


def test_the_report_counts_by_status_and_explains_its_own_mark() -> None:
    text = render_text([_catalog()])

    assert "ghc  https://api.githubcopilot.com" in text
    assert "6 models, 2 routable, 1 disabled, 1 no-driver, 1 no-endpoints, 1 policy:unconfigured" in text
    assert "ws:/responses*" in text
    assert "* advertised by upstream, no driver in this proxy" in text


def test_the_summary_line_cannot_be_split_by_upstream_text() -> None:
    """The summary repeats the status words, and a status can be an upstream policy state. A newline in one would put upstream text on its own line inside the report's structure."""
    raw = {"data": [_model("gated", policy={"state": "unconfigured\nFAKE SUMMARY LINE"})]}

    text = render_text([_catalog(raw=raw, disabled=[])])
    summary = text.splitlines()[1]

    assert "FAKE SUMMARY LINE" not in text.replace("unconfiguredFAKE SUMMARY LINE", "")
    assert summary.endswith("1 policy:unconfiguredFAKE SUMMARY LINE")


def test_the_report_leaves_out_a_mark_nothing_carries() -> None:
    text = render_text([_catalog(raw={"data": [_model("routable")]}, disabled=[])])

    assert "no driver in this proxy" not in text


def test_a_provider_with_an_empty_catalog_says_so() -> None:
    text = render_text([_catalog(raw={"data": []}, disabled=[])])

    assert "upstream offered no models" in text
    assert "0 models, 0 routable" in text


def test_no_row_carries_trailing_whitespace() -> None:
    # The last column is unpadded so a pasted report does not arrive full of invisible spaces.
    text = render_text([_catalog()])

    assert not [line for line in text.splitlines() if line != line.rstrip()]


def test_one_model_occupies_exactly_one_line_whatever_upstream_put_in_it() -> None:
    """A newline inside an id used to draw a second physical line, which reads as another model and puts its remaining columns under the wrong headings."""
    raw = {
        "data": [
            _model("wrapped\nFAKE-MODEL", vendor="Acme\nINJECTED"),
            _model("coloured\x1b[31mRED\x1b[0m"),
        ]
    }
    catalog = _catalog(raw=raw, disabled=[])

    text = render_text([catalog])
    body = text.splitlines()[3:]

    assert "\x1b" not in text
    assert "FAKE-MODEL" not in text.replace("wrappedFAKE-MODEL", "")
    # Header plus exactly one line per model, and nothing left dangling under the wrong column.
    assert len(body) == len(catalog.rows) + 1
    assert not [line for line in body if line.startswith("INJECTED")]


def test_columns_stay_aligned_when_a_cell_is_double_width() -> None:
    """A CJK character occupies two terminal columns; padding by code point steps every later column left by one per character.

    The assertion has to measure in cells too — `str.index` counts code points and would call the misaligned version correct.
    """
    raw = {"data": [_model("模型-一"), _model("plain")]}

    lines = render_text([_catalog(raw=raw, disabled=[])]).splitlines()[3:]
    status_column = [cell_len(line[: line.index("ok")]) for line in lines[1:]]

    assert len(set(status_column)) == 1, lines


def test_entries_that_produced_no_row_are_named_in_the_summary() -> None:
    raw: dict[str, Any] = {"data": [_model("fine"), "not-an-object", 42]}

    text = render_text([_catalog(raw=raw, disabled=[])])

    assert "1 models, 1 routable (2 unreadable entries skipped)" in text


def test_a_clean_catalog_says_nothing_about_unreadable_entries() -> None:
    # The negative control: the clause must not appear when there is nothing to report.
    assert "unreadable" not in render_text([_catalog()])


def test_json_keeps_every_decoded_field_keyed_by_provider() -> None:
    """`--json` exists so nothing is projected away. It is the decoded payload, not the upstream bytes: whitespace and escape spelling were gone before this code ran, so that is what the help text now claims."""
    document = json.loads(render_json([_catalog()]))

    assert document == {"ghc": CATALOG}


def test_json_is_not_stripped_of_control_characters_like_the_table_is() -> None:
    """The table strips them because they break its layout; the payload must still show what upstream actually sent."""
    raw = {"data": [_model("wrapped\nFAKE")]}

    document = json.loads(render_json([_catalog(raw=raw, disabled=[])]))

    assert document["ghc"]["data"][0]["id"] == "wrapped\nFAKE"


def test_a_missing_token_is_reported_with_the_command_that_fixes_it() -> None:
    from app.auth.providers import NoGitHubToken

    assert "ghc-api-proxy auth" in describe_failure(NoGitHubToken("no token"))
    assert describe_failure(RuntimeError("upstream said 503")) == "upstream said 503"
    # An exception carrying no message still has to name itself.
    assert describe_failure(TimeoutError()) == "TimeoutError"


class _FakeProvider(GithubCopilotProvider):
    """A provider that answers from a canned payload, or refuses to.

    Subclassed rather than duck-typed because `collect_catalogs` checks the concrete type before trusting a provider to have a catalog — a stand-in that skipped that check would test a path production never takes.
    """

    def __init__(self, name: str, *, raw: dict[str, Any] | None = None, fails: str = "") -> None:
        self._name_ = name
        self._raw_ = raw or {"data": []}
        self._fails = fails

    @property
    def name(self) -> str:
        return self._name_

    @property
    def base_url(self) -> str:
        return f"https://{self._name_}.test"

    @property
    def raw_catalog(self) -> dict[str, Any]:
        return self._raw_

    async def refresh_catalog(self) -> bool:
        if self._fails:
            raise RuntimeError(self._fails)
        return True


class _FakeRegistry:
    def __init__(self, providers: dict[str, GithubCopilotProvider]) -> None:
        self._providers = providers

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._providers)

    def get(self, name: str) -> GithubCopilotProvider:
        return self._providers[name]


class _RecordingClient:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


def _two_provider_config() -> ProxyConfig:
    return ProxyConfig.model_validate(
        {
            "model_providers": {
                "healthy": {"type": "github_copilot"},
                "broken": {"type": "github_copilot", "disabled_models": ["blocked"]},
            },
            "default_model_provider": "healthy",
        }
    )


def _patch_collection(
    monkeypatch: pytest.MonkeyPatch,
    providers: dict[str, GithubCopilotProvider],
) -> _RecordingClient:
    client = _RecordingClient()

    def build_client(config: ProxyConfig) -> _RecordingClient:
        return client

    def build_chain(config: ProxyConfig, *, http_client: object) -> SimpleNamespace:
        return SimpleNamespace(providers=_FakeRegistry(providers))

    monkeypatch.setattr("app.debug.models.build_http_client", build_client)
    monkeypatch.setattr("app.debug.models.build_chain", build_chain)
    return client


async def test_one_dead_provider_does_not_hide_a_healthy_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reason failures are collected instead of raised. An expired token on one upstream must not cost the operator the other upstream's answer."""
    client = _patch_collection(
        monkeypatch,
        {
            "healthy": _FakeProvider("healthy", raw=CATALOG),
            "broken": _FakeProvider("broken", fails="upstream said 503"),
        },
    )

    catalogs, failures = await collect_catalogs(_two_provider_config())

    assert [catalog.name for catalog in catalogs] == ["healthy"]
    assert [(failure.name, failure.reason) for failure in failures] == [
        ("broken", "upstream said 503")
    ]
    assert client.closed


async def test_the_named_provider_is_the_only_one_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    # `--provider` must not quietly fetch the others too; each fetch is an authenticated round trip.
    client = _patch_collection(
        monkeypatch,
        {
            "healthy": _FakeProvider("healthy", raw=CATALOG),
            "broken": _FakeProvider("broken", fails="must not be asked"),
        },
    )

    catalogs, failures = await collect_catalogs(_two_provider_config(), "healthy")

    assert [catalog.name for catalog in catalogs] == ["healthy"]
    assert failures == ()
    assert client.closed


async def test_each_provider_gets_its_own_disabled_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """The disabled list is per provider in the schema; reading the wrong one marks the wrong model."""
    _patch_collection(
        monkeypatch,
        {
            "healthy": _FakeProvider("healthy", raw=CATALOG),
            "broken": _FakeProvider("broken", raw=CATALOG),
        },
    )

    catalogs, _ = await collect_catalogs(_two_provider_config())
    by_name = {catalog.name: catalog for catalog in catalogs}

    def disabled(name: str) -> set[str]:
        return {row.id for row in by_name[name].rows if row.status == "disabled"}

    assert disabled("healthy") == set()
    assert disabled("broken") == {"blocked"}


async def test_the_outbound_client_is_closed_even_when_the_chain_cannot_be_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The client is created before the chain, so the failure that happens most often — a config the composition root rejects — is the one that would leak it.
    client = _RecordingClient()

    def build_client(config: ProxyConfig) -> _RecordingClient:
        return client

    def explode(config: ProxyConfig, *, http_client: object) -> object:
        raise ProviderNotConfigured("")

    monkeypatch.setattr("app.debug.models.build_http_client", build_client)
    monkeypatch.setattr("app.debug.models.build_chain", explode)

    with pytest.raises(ProviderNotConfigured):
        await collect_catalogs(ProxyConfig())

    assert client.closed


def _config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        "model_providers:\n  ghc:\n    type: github_copilot\ndefault_model_provider: ghc\n",
        encoding="utf-8",
    )
    return path


def test_cli_prints_the_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def collect(config: object, only: str | None) -> tuple[Any, Any]:
        assert only is None
        return (_catalog(),), ()

    monkeypatch.setattr("app.cli.collect_catalogs", collect)

    result = runner.invoke(app, ["debug", "models", "--config", str(_config_file(tmp_path))])

    assert result.exit_code == 0, result.output
    # The whole rendered report, not two words that a hardcoded string could also satisfy.
    assert render_text([_catalog()]) in result.stdout


def test_cli_reports_a_bad_config_without_a_traceback(tmp_path: Path) -> None:
    """A mistyped config is ordinary operator input, and a stack naming `app.cli` does not point at the key they got wrong."""
    path = tmp_path / "config.yaml"
    path.write_text("model_providers:\n  ghc:\n    type: not_a_provider\n", encoding="utf-8")

    result = runner.invoke(app, ["debug", "models", "--config", str(path)])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    # Pydantic's field path survives: it is the part that says which key to fix.
    assert "model_providers.ghc.type" in result.stderr


def test_cli_reports_a_missing_config_without_a_traceback(tmp_path: Path) -> None:
    result = runner.invoke(app, ["debug", "models", "--config", str(tmp_path / "absent.yaml")])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "configuration file not found" in result.stderr


def test_cli_narrows_to_one_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str | None] = []

    async def collect(config: object, only: str | None) -> tuple[Any, Any]:
        seen.append(only)
        return (_catalog(),), ()

    monkeypatch.setattr("app.cli.collect_catalogs", collect)

    result = runner.invoke(
        app,
        ["debug", "models", "--config", str(_config_file(tmp_path)), "--provider", "ghc"],
    )

    assert result.exit_code == 0, result.output
    assert seen == ["ghc"]


def test_cli_refuses_a_provider_the_config_does_not_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refused before any network call, and told which names would have worked."""

    async def collect(config: object, only: str | None) -> tuple[Any, Any]:
        raise AssertionError("must not reach upstream for a name the config does not have")

    monkeypatch.setattr("app.cli.collect_catalogs", collect)

    result = runner.invoke(
        app,
        ["debug", "models", "--config", str(_config_file(tmp_path)), "--provider", "nope"],
    )

    assert result.exit_code == 2
    assert "configured: ghc" in result.output


def test_cli_reports_a_failed_provider_and_exits_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider that could not be read is named on stderr, and the ones that answered are still printed on stdout."""

    async def collect(config: object, only: str | None) -> tuple[Any, Any]:
        return (_catalog(),), (CatalogFailure("other", "no token — run `ghc-api-proxy auth`"),)

    monkeypatch.setattr("app.cli.collect_catalogs", collect)

    result = runner.invoke(app, ["debug", "models", "--config", str(_config_file(tmp_path))])

    assert result.exit_code == 1
    # Checked on the separate streams: a failure printed to stdout would corrupt a piped report while still satisfying a merged-output assertion.
    assert "error: other: no token" in result.stderr
    assert "error:" not in result.stdout
    assert "ghc  https://api.githubcopilot.com" in result.stdout


def test_cli_emits_json_on_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def collect(config: object, only: str | None) -> tuple[Any, Any]:
        return (_catalog(),), ()

    monkeypatch.setattr("app.cli.collect_catalogs", collect)

    result = runner.invoke(
        app,
        ["debug", "models", "--config", str(_config_file(tmp_path)), "--json"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"ghc": CATALOG}
