"""Which `cache_control` keys reach an Anthropic Messages upstream.

The shape under test is the one a user's machine actually sent on 2026-08-24 and got a 400 for — `{"type": "ephemeral", "scope": …}` on `system[1]` — and the refusal paths quoted here are upstream's own words from `exp/260824-beta-and-cache-control-probe/`, not invented ones.

**The position set is wider than the reported failure.** The 400 named `system.1`; the request schema allows a marker on the request itself, on system blocks, on message content blocks, inside `tool_result` / `search_result` / `document.source` content lists, and on tools. Tests written from the reported path alone would leave every other position uncovered, which is how the first version of this pass shipped missing three of them.

One test goes through `build_chain` and `handle` rather than calling the subscriber. Being registered is not being run: every assertion that calls `prune_cache_control_fields` directly would stay green if nobody had wired it up.
"""

from collections.abc import Mapping
from typing import Any

import httpx2
import pytest

from app.config.loading import bundled_config_values
from app.config.schema import ProxyConfig
from app.model_provider import ModelDescriptor, ModelEndpoint
from app.pipeline.driver import handle, handle_count_tokens
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.subscribers.anthropic_cache_control import (
    compile_sanitize_table,
    prune_cache_control_fields,
    refused_fields_for,
)
from app.pipeline.translation_driver.semantic import LossCode
from app.server.composition import build_chain

# What Claude Code sends once it has negotiated `prompt-caching-scope-2026-01-05`. Upstream refuses it whether or not that beta rides along — measured, both ways.
REFUSED: dict[str, Any] = {"type": "ephemeral", "scope": "organization"}
# What upstream accepts. `ttl` is in here because it was sent and accepted, not because it looked harmless.
ACCEPTED: dict[str, Any] = {"type": "ephemeral", "ttl": "1h"}

# What `bundled-config.yaml` ships, compiled. The direct-call tests pass this explicitly rather than leaning on a default, because an empty table makes `sanitize` a no-op and a test that forgot it would pass for the wrong reason.
TABLE = compile_sanitize_table({"claude-.*": ["scope"]})

SONNET = ModelDescriptor(
    id="claude-sonnet-5",
    endpoints=frozenset({ModelEndpoint.ANTHROPIC_MESSAGES}),
    adaptive_thinking=True,
)


def context_for(
    payload: dict[str, Any], *, target: WireFormat = WireFormat.ANTHROPIC_MESSAGES
) -> RequestContext:
    return RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-sonnet-4-5",
        payload=payload,
        resolved_model="claude-sonnet-5",
        target_format=target,
        model_descriptor=SONNET,
    )


def marked_body() -> dict[str, Any]:
    """A body carrying a refused marker in the three places upstream named in its own error paths.

    Three because those are the three the 400s quoted — `system.1.cache_control…`, `messages.0.content.0.text.cache_control…` and `tools.0.custom.cache_control…`, each a separate schema upstream. **Not the full position set**: the top level and the nested content lists have their own tests, because a fixture that carried everything would let a pass that missed one of them still look covered here.
    """
    return {
        "model": "claude-sonnet-5",
        "system": [
            {"type": "text", "text": "You are helpful."},
            {"type": "text", "text": "Be concise.", "cache_control": dict(REFUSED)},
        ],
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "hi", "cache_control": dict(REFUSED)}],
            }
        ],
        "tools": [
            {"name": "get_weather", "input_schema": {}, "cache_control": dict(REFUSED)}
        ],
    }


async def test_the_key_that_earned_the_400_is_removed_from_all_three_layers() -> None:
    """The whole repair, on the input that is measured rather than imagined."""
    context = context_for(marked_body())

    await prune_cache_control_fields(context, mode="sanitize", table=TABLE)

    payload = context.payload
    assert payload["system"][1]["cache_control"] == {"type": "ephemeral"}
    assert payload["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert payload["tools"][0]["cache_control"] == {"type": "ephemeral"}


async def test_the_breakpoint_itself_survives_everywhere_it_was_placed() -> None:
    """The removal must not become "drop the marker".

    `cache_control` marks a position in the prompt. Removing the whole object where the client put one would move where the cached prefix ends — a silent behaviour change dressed as a compatibility fix — so what is asserted here is that a marker is still *present* at all three positions, not merely that `scope` is gone.
    """
    context = context_for(marked_body())

    await prune_cache_control_fields(context, mode="sanitize", table=TABLE)

    payload = context.payload
    assert "cache_control" in payload["system"][1]
    assert "cache_control" in payload["messages"][0]["content"][0]
    assert "cache_control" in payload["tools"][0]


async def test_a_ttl_upstream_accepts_is_not_taken_away() -> None:
    """Measured: `{type: ephemeral, ttl: "1h"}` answers 200, with or without its own beta.

    The negative control on the shipped table. `ttl` is not in it, so it must survive — a pass that normalised every marker to a bare `{"type": "ephemeral"}` would satisfy the test above and quietly shorten every cache the client asked to keep for an hour.
    """
    context = context_for(
        {"model": "claude-sonnet-5", "system": [{"type": "text", "text": "x", "cache_control": dict(ACCEPTED)}]}
    )

    await prune_cache_control_fields(context, mode="sanitize", table=TABLE)

    assert context.payload["system"][0]["cache_control"] == ACCEPTED
    assert "conversion_losses" not in context.extras


async def test_each_removal_is_recorded_with_its_path_where_the_log_line_reads_it() -> None:
    """`scope` decides how widely a cached prefix is shared, so dropping it changes what the cache does.

    One loss per marker, each carrying its path. A reader of the record is asking *which* breakpoints were altered, and a single entry saying "3 markers" cannot answer that — so the count and the paths are both asserted, not just that some loss exists.

    Asserted on `conversion_losses` specifically rather than on "some loss exists": that key is the one `observability/request_trace.py` reads, so a loss recorded anywhere else reaches nobody.
    """
    context = context_for(marked_body())

    await prune_cache_control_fields(context, mode="sanitize", table=TABLE)

    losses = context.extras["conversion_losses"]
    assert {loss.code for loss in losses} == {LossCode.CACHE_CONTROL_FIELD_NOT_CARRIED}
    paths = sorted(loss.detail.split(".cache_control")[0] for loss in losses)
    assert paths == ["messages.0.content.0", "system.1", "tools.0"]
    assert all("scope" in loss.detail for loss in losses)


async def test_a_marker_with_nothing_upstream_accepts_goes_away_whole() -> None:
    """An empty `cache_control` is a shape nobody measured, so the marker is removed instead of emptied."""
    context = context_for(
        {"model": "claude-sonnet-5", "system": [{"type": "text", "text": "x", "cache_control": {"scope": "organization"}}]}
    )

    await prune_cache_control_fields(context, mode="sanitize", table=TABLE)

    assert "cache_control" not in context.payload["system"][0]


async def test_a_body_bound_for_responses_is_left_alone() -> None:
    """The route decides, not the inbound format. The Responses endpoint has its own answer about `cache_control` and it is not this one."""
    body = {
        "model": "gpt-5.6-sol",
        "system": [{"type": "text", "text": "x", "cache_control": dict(REFUSED)}],
    }
    context = context_for(body, target=WireFormat.OPENAI_RESPONSES)

    await prune_cache_control_fields(context, mode="sanitize", table=TABLE)

    assert context.payload["system"][0]["cache_control"] == REFUSED


async def test_running_it_twice_changes_nothing_and_records_nothing_new() -> None:
    """`attempt.prepare` fires once per attempt, so a retry re-runs this over the body the last pass already edited."""
    context = context_for(marked_body())

    await prune_cache_control_fields(context, mode="sanitize", table=TABLE)
    after_first = context.payload["system"][1]["cache_control"]
    recorded = len(context.extras["conversion_losses"])
    await prune_cache_control_fields(context, mode="sanitize", table=TABLE)

    assert context.payload["system"][1]["cache_control"] == after_first
    assert len(context.extras["conversion_losses"]) == recorded


async def test_a_string_system_and_a_string_content_are_not_walked_into() -> None:
    """Both fields are legally a bare string, which carries no marker and no place to put one."""
    context = context_for(
        {
            "model": "claude-sonnet-5",
            "system": "You are helpful.",
            "messages": [{"role": "user", "content": "hi"}],
        }
    )

    await prune_cache_control_fields(context, mode="sanitize", table=TABLE)

    assert context.payload["system"] == "You are helpful."
    assert "conversion_losses" not in context.extras


class CapableProvider:
    """A provider whose catalog answer lets routing reach `claude-sonnet-5`."""

    name = "ghc"

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.counted: list[dict[str, Any]] = []

    @property
    def available_ids(self) -> frozenset[str]:
        return frozenset({"claude-sonnet-5"})
    @property
    def raw_catalog(self) -> Mapping[str, Any]:
        return {}


    # Reporting-only members of the provider protocol, here so this stub satisfies it. Nothing on this test's path reads them; `/api/status` does.
    @property
    def disabled_ids(self) -> frozenset[str]:
        return frozenset()

    @property
    def base_url(self) -> str:
        return "https://stub.invalid"

    @property
    def catalog_refreshed_at(self) -> str:
        return "2026-08-27T00:00:00+00:00"

    def describe(self, model_id: str) -> ModelDescriptor | None:
        return SONNET if model_id == "claude-sonnet-5" else None

    async def refresh_catalog(self) -> bool:
        return False

    async def send(
        self,
        endpoint: ModelEndpoint,
        payload: Any,
        *,
        model_id: str,
        stream: bool = False,
        extra_headers: Any = None,
    ) -> httpx2.Response:
        self.sent.append(dict(payload))
        return httpx2.Response(200)

    async def count_tokens(self, payload: Any, *, model_id: str) -> httpx2.Response:
        self.counted.append(dict(payload))
        # Carries a request because the caller calls `raise_for_status()`, which needs one.
        return httpx2.Response(
            200,
            json={"input_tokens": 7},
            request=httpx2.Request("POST", "https://upstream.invalid/v1/messages/count_tokens"),
        )


async def test_the_refused_key_does_not_reach_the_wire_through_the_real_chain() -> None:
    """The only test here that fails if nobody registered the subscriber.

    Every assertion above calls the function directly and would sail through a chain that never invokes it — which is the exact shape this project has been bitten by before, a guard left wired to a path production no longer takes.
    """
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "ghc",
            "model_providers": {"ghc": {"type": "github_copilot"}},
            "model_mappings": {"claude-sonnet-4-5": "claude-sonnet-5"},
            # Explicit, because the default is `passthrough` and the user ruled that literal: without this line the request goes out carrying `scope`, which is the configured behaviour rather than a bug.
            "hook_fix_anthropic_request": {
                "cache_control": "sanitize",
                "cache_control_sanitize": {"claude-.*": ["scope"]},
            },
        }
    )
    provider = CapableProvider()
    chain = build_chain(config, http_client=httpx2.AsyncClient(), providers={"ghc": provider})
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-sonnet-4-5",
        payload={
            "model": "claude-sonnet-4-5",
            "max_tokens": 64,
            "system": [
                {"type": "text", "text": "You are helpful."},
                {"type": "text", "text": "Be concise.", "cache_control": dict(REFUSED)},
            ],
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    await handle(chain, context)

    [sent] = provider.sent
    assert sent["system"][1]["cache_control"] == {"type": "ephemeral"}


async def test_the_request_s_own_cache_control_is_pruned_too() -> None:
    """Top-level automatic caching — the position with no block to hang off, and the one this pass first missed.

    Anthropic's `MessageCreateParams` carries `cache_control` on the request itself, meaning "put a marker on the last cacheable block". Nothing that walks `system`, `messages` or `tools` reaches it.
    """
    context = context_for({"model": "claude-sonnet-5", "cache_control": dict(REFUSED), "messages": []})

    await prune_cache_control_fields(context, mode="sanitize", table=TABLE)

    assert context.payload["cache_control"] == {"type": "ephemeral"}
    assert any("(request)" in loss.detail for loss in context.extras["conversion_losses"])


async def test_a_marker_nested_inside_a_tool_result_is_pruned() -> None:
    """`tool_result.content` is a list of blocks, each of which may carry its own marker.

    A pass that only looked at the outer block would leave this one on the wire — and the outer `tool_result` here carries no marker at all, so nothing shallower would even flag the message.
    """
    context = context_for(
        {
            "model": "claude-sonnet-5",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_1",
                            "content": [
                                {"type": "text", "text": "18C", "cache_control": dict(REFUSED)}
                            ],
                        }
                    ],
                }
            ],
        }
    )

    await prune_cache_control_fields(context, mode="sanitize", table=TABLE)

    nested = context.payload["messages"][0]["content"][0]["content"][0]
    assert nested["cache_control"] == {"type": "ephemeral"}
    assert any(
        "messages.0.content.0.content.0" in loss.detail
        for loss in context.extras["conversion_losses"]
    )


async def test_a_field_no_entry_names_is_left_alone() -> None:
    """The ruled shape: name what is known to fail, leave the rest.

    This is the price of the 2026-08-24 denylist ruling stated as a test rather than left implicit. A field Anthropic invents tomorrow travels to a strict-schema endpoint and costs the whole request until someone adds a line to `cache_control_sanitize`. An allowlist would have caught it; the ruling took the other side, and the reason it did is in spec §7.2. Asserting it here means the day that behaviour is questioned, the answer is a test with a name rather than an archaeology exercise.
    """
    context = context_for(
        {
            "model": "claude-sonnet-5",
            "system": [
                {"type": "text", "text": "x", "cache_control": {"type": "ephemeral", "invented_2027": "x"}}
            ],
        }
    )

    await prune_cache_control_fields(context, mode="sanitize", table=TABLE)

    assert context.payload["system"][0]["cache_control"] == {
        "type": "ephemeral",
        "invented_2027": "x",
    }
    assert "conversion_losses" not in context.extras


async def test_a_field_the_table_does_name_is_removed_even_if_it_is_not_scope() -> None:
    """And the other half: nothing here is hardcoded to `scope`.

    Every other case in this file uses `scope`, so an implementation that ignored the table and removed that one key by name would keep them all green. This one names a different field and expects it gone.
    """
    context = context_for(
        {
            "model": "claude-sonnet-5",
            "system": [
                {"type": "text", "text": "x", "cache_control": {"type": "ephemeral", "invented_2027": "x"}}
            ],
        }
    )

    await prune_cache_control_fields(
        context, mode="sanitize", table=compile_sanitize_table({"claude-.*": ["invented_2027"]})
    )

    assert context.payload["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert any("invented_2027" in loss.detail for loss in context.extras["conversion_losses"])


async def test_a_model_no_entry_names_keeps_everything() -> None:
    """Per-model is the other half of the ruling, and the table is keyed on the **resolved** model.

    A capability belongs to the model that answers, so the entry is matched against what upstream receives rather than the alias the client asked for. This context resolves to a model the table does not name.
    """
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="opus",
        payload={
            "model": "gpt-5.6-sol",
            "system": [{"type": "text", "text": "x", "cache_control": dict(REFUSED)}],
        },
        resolved_model="gpt-5.6-sol",
        target_format=WireFormat.ANTHROPIC_MESSAGES,
        model_descriptor=SONNET,
    )

    await prune_cache_control_fields(context, mode="sanitize", table=TABLE)

    assert context.payload["system"][0]["cache_control"] == REFUSED
    assert "conversion_losses" not in context.extras


async def test_a_translated_request_bound_for_anthropic_is_pruned() -> None:
    """The guard reads the *target* format, and this is the half that proves it.

    Its sibling above checks a Responses target is left alone; both would stay green if the guard were changed to read the inbound format instead, because every other context here is Anthropic inbound. This one is not: it arrives as Responses and is translated *into* Anthropic, which is exactly the request that would slip through such a change.
    """
    context = RequestContext(
        inbound_format=WireFormat.OPENAI_RESPONSES,
        requested_model="claude-sonnet-4-5",
        payload={
            "model": "claude-sonnet-5",
            "system": [{"type": "text", "text": "x", "cache_control": dict(REFUSED)}],
        },
        resolved_model="claude-sonnet-5",
        target_format=WireFormat.ANTHROPIC_MESSAGES,
        model_descriptor=SONNET,
    )

    await prune_cache_control_fields(context, mode="sanitize", table=TABLE)

    assert context.payload["system"][0]["cache_control"] == {"type": "ephemeral"}


async def test_the_counting_leg_measures_the_body_that_would_actually_be_sent() -> None:
    """Counting has to see the same pruning generation does, and only this path can prove it.

    A sibling subscriber already paid for this lesson: adding `if context.extras.get(COUNTING_ONLY): return` left every unit test green because none of them reached `handle_count_tokens` with a body the module would touch. Here the same mutation would let `/v1/messages/count_tokens` measure a body carrying `scope` — a body the real endpoint answers 400 to, so the number would describe a request nobody could send.
    """
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "ghc",
            "model_providers": {"ghc": {"type": "github_copilot"}},
            "model_mappings": {"claude-sonnet-4-5": "claude-sonnet-5"},
            # Explicit, because the default is `passthrough` and the user ruled that literal: without this line the request goes out carrying `scope`, which is the configured behaviour rather than a bug.
            "hook_fix_anthropic_request": {
                "cache_control": "sanitize",
                "cache_control_sanitize": {"claude-.*": ["scope"]},
            },
        }
    )
    provider = CapableProvider()
    chain = build_chain(config, http_client=httpx2.AsyncClient(), providers={"ghc": provider})
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-sonnet-4-5",
        payload={
            "model": "claude-sonnet-4-5",
            "system": [{"type": "text", "text": "x", "cache_control": dict(REFUSED)}],
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    await handle_count_tokens(chain, context)

    [counted] = provider.counted
    assert counted["system"][0]["cache_control"] == {"type": "ephemeral"}


async def test_passthrough_forwards_the_refused_key_untouched() -> None:
    """The ruled default, and the one behaviour it would be easiest to quietly get wrong.

    The user ruled on 2026-08-24 that `passthrough` means what `config.example.yaml` says: forward the client's markers as-is, including a key this upstream refuses. So this asserts the request goes out *broken* — upstream will answer 400 — because that is the configured contract, not an oversight. An implementation that sanitised "just this one harmless key" under the default would pass every other test in this file.
    """
    context = context_for(marked_body())

    await prune_cache_control_fields(context, mode="passthrough")

    payload = context.payload
    assert payload["system"][1]["cache_control"] == REFUSED
    assert payload["messages"][0]["content"][0]["cache_control"] == REFUSED
    assert payload["tools"][0]["cache_control"] == REFUSED
    assert "conversion_losses" not in context.extras


async def test_an_empty_table_makes_the_default_a_no_op() -> None:
    """`sanitize` with nothing configured touches nothing, and that is by design.

    The table names models known to refuse a field; with no table there is no such model, so the mode has nothing to do. This matters because `ProxyConfig.model_validate` does not read `bundled-config.yaml` — every test that builds a config by hand gets the empty table, and would quietly prove nothing about the shipped behaviour. The test below is the one that covers what an operator actually gets.
    """
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "ghc",
            "model_providers": {"ghc": {"type": "github_copilot"}},
            "model_mappings": {"claude-sonnet-4-5": "claude-sonnet-5"},
        }
    )
    provider = CapableProvider()
    chain = build_chain(config, http_client=httpx2.AsyncClient(), providers={"ghc": provider})
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-sonnet-4-5",
        payload={
            "model": "claude-sonnet-4-5",
            "max_tokens": 64,
            "system": [{"type": "text", "text": "x", "cache_control": dict(REFUSED)}],
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    await handle(chain, context)

    [sent] = provider.sent
    assert sent["system"][0]["cache_control"] == REFUSED


async def test_disabled_removes_every_marker() -> None:
    """The third mode. `disabled` is not "sanitize harder" — no breakpoint survives it at all.

    The record has to say so in the right words: one entry per *marker* (not per key), and blaming the configuration rather than upstream. Under `disabled` upstream refuses nothing — `{"type": "ephemeral", "ttl": "1h"}` is a body it accepts — so a record saying "upstream refuses it" would send the next reader hunting an upstream problem that does not exist.
    """
    context = context_for(
        {
            "model": "claude-sonnet-5",
            "system": [{"type": "text", "text": "x", "cache_control": dict(ACCEPTED)}],
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}]}
            ],
        }
    )

    await prune_cache_control_fields(context, mode="disabled")

    assert "cache_control" not in context.payload["system"][0]
    assert "cache_control" not in context.payload["messages"][0]["content"][0]
    losses = context.extras["conversion_losses"]
    assert len(losses) == 2, "one per marker, not one per key"
    assert all("disabled by configuration" in loss.detail for loss in losses)
    assert not any("upstream refuses" in loss.detail for loss in losses)


def test_the_unimplemented_mode_is_refused_at_startup() -> None:
    """`proxied` would strip the client's breakpoints and inject the proxy's own; only stripping exists.

    Refused rather than silently treated as `passthrough`, because the quiet version is an operator who configured the proxy to own prompt caching, gets no error, and is billed as though nobody owned it.
    """
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "ghc",
            "model_providers": {"ghc": {"type": "github_copilot"}},
            "hook_fix_anthropic_request": {"cache_control": "proxied"},
        }
    )

    with pytest.raises(ValueError, match="proxied"):
        build_chain(config, http_client=httpx2.AsyncClient(), providers={"ghc": CapableProvider()})


async def test_out_of_the_box_the_shipped_config_strips_scope_from_a_claude_model() -> None:
    """What an operator gets with no config file at all — the case the whole ruling is about.

    Every other chain-level test here builds its config with `ProxyConfig.model_validate`, which does **not** read `bundled-config.yaml`; they therefore exercise an empty table and cannot see whether the shipped one is right, present, or even syntactically valid. This one layers the real bundled values, so it fails if the table is deleted, renamed, its regex stops matching Claude models, or the default mode is moved off `sanitize`.
    """
    bundled = bundled_config_values()
    config = ProxyConfig.model_validate(
        {
            **bundled,
            "default_model_provider": "ghc",
            "model_providers": {"ghc": {"type": "github_copilot"}},
            "model_mappings": {"claude-sonnet-4-5": "claude-sonnet-5"},
        }
    )
    assert config.hook_fix_anthropic_request.cache_control == "sanitize"

    provider = CapableProvider()
    chain = build_chain(config, http_client=httpx2.AsyncClient(), providers={"ghc": provider})
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-sonnet-4-5",
        payload={
            "model": "claude-sonnet-4-5",
            "max_tokens": 64,
            "system": [{"type": "text", "text": "x", "cache_control": dict(REFUSED)}],
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    await handle(chain, context)

    [sent] = provider.sent
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_the_shipped_table_names_scope_for_claude_and_nothing_for_the_rest() -> None:
    """The table's contents, asserted where a reader can find them.

    Not a restatement of the YAML for its own sake: `claude-.*` is a *regular expression*, and the failure mode worth guarding is an entry that looks right and matches nothing — which is exactly what happened to the neighbouring `strip_anthropic_beta_flags` table, whose only key is mapped away by `model_mappings` and therefore never fires.
    """
    table = compile_sanitize_table(
        ProxyConfig.model_validate(bundled_config_values()).hook_fix_anthropic_request.cache_control_sanitize
    )

    for model in ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4.5", "claude-sonnet-4.6"):
        assert refused_fields_for(model, table) == frozenset({"scope"}), model
    for model in ("gpt-5.6-sol", "gpt-5.6-luna", "grok-4.6"):
        assert refused_fields_for(model, table) == frozenset(), model
