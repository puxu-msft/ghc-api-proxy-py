"""What the client's headers and `context_management` look like by the time upstream sees them.

Both cover the same defect from opposite ends. Claude Code sends `anthropic-beta` with ten tokens and `context_management: {"edits": null}` on every request; the chain forwarded neither correctly, so upstream refused a field the beta would have enabled and the client saw a 502. Measured against the live upstream on 2026-08-18: `{"edits": null}` is refused, `{"edits": []}` is accepted, and without the beta header the field is not recognised at all.
"""

from typing import Any

import httpx2

from app.config.schema import FixAnthropicRequestHook, ProxyConfig
from app.model_provider import ModelDescriptor, ModelEndpoint
from app.pipeline.anthropic_request_hook import fix_anthropic_request, normalize_context_management
from app.pipeline.driver import shape_request
from app.pipeline.request import RequestContext, WireFormat
from app.pipeline.request_headers import (
    GATEWAY_UNSUPPORTED_BETAS,
    apply_path_header_policy,
    compile_beta_flag_denials,
    forwarded_client_headers,
    strip_denied_beta_flags,
    strip_gateway_unsupported_betas,
)
from app.server.composition import build_chain
from app.server.inbound import build_context
from app.server.routes.table import ROUTES


def test_the_beta_header_is_forwarded() -> None:
    """The one that decides whether a real request works at all."""
    forwarded = forwarded_client_headers(
        {"anthropic-beta": "context-management-2025-06-27,effort-2025-11-24"}
    )
    assert forwarded == {"anthropic-beta": "context-management-2025-06-27,effort-2025-11-24"}


def test_the_blacklist_is_case_insensitive_for_every_entry_the_document_names() -> None:
    """`message-format-reshape.md` made this explicit on 2026-08-22, and it had never been pinned.

    A client picks its own case and HTTP does not care; a blacklist that did would leak on the first client that capitalised differently. Every spelling of every entry the document lists, plus the one it added in the same edit — `Authorization`, which is the one that would have travelled beside our own credential.
    """
    probe = {
        "Authorization": "Bearer client-secret",
        "AUTHORIZATION": "Bearer shouty",
        "AuThOrIzAtIoN": "Bearer mixed",
        "Cookie": "session=1",
        "X-Api-Key": "sk-client",
        "HOST": "proxy.local",
        "Content-Length": "999",
        "Content-Encoding": "gzip",
        "Accept-Encoding": "br",
        "X-Forwarded-For": "10.0.0.1",
        "Forwarded": "for=10.0.0.1",
        "Anthropic-Beta": "context-management-2025-06-27",
    }
    assert forwarded_client_headers(probe) == {
        "anthropic-beta": "context-management-2025-06-27"
    }


def test_credentials_never_survive_the_floor() -> None:
    """The floor's one job, and the reason it runs at parse time rather than at the send site.

    `message-format-reshape.md` lists `Cookie` and `X-Api-Key` for the direct path and does not mention `authorization`, but the reference implementation the document's TODO points at guards that one twice — and it has to be guarded, because the upstream request carries a Copilot Chat credential of its own. After this returns, nothing downstream is holding anything the client authenticated with.
    """
    forwarded = forwarded_client_headers(
        {
            "authorization": "Bearer client-secret",
            "x-api-key": "sk-client",
            "cookie": "session=1",
            "host": "proxy.local",
            "content-length": "999",
            "accept-encoding": "br",
            "x-forwarded-for": "10.0.0.1",
            "anthropic-beta": "context-management-2025-06-27",
        }
    )
    assert forwarded == {"anthropic-beta": "context-management-2025-06-27"}


def test_the_floor_is_a_blacklist_so_an_unknown_client_header_survives_it() -> None:
    """Ruled 2026-08-22 and the opposite of what this module used to do.

    Under the old allowlist only `anthropic-beta` and `anthropic-version` ever travelled. The document asks for a blacklist on the direct path, so a header nobody enumerated now reaches the next stage — which is the point, and also why the floor above it has to be right.

    `user-agent` surviving *here* is not the same as it reaching upstream: it collides with a header the proxy owns, and `GhcApiClient.request_headers` is what drops it. That is a separate test, in a separate file, because it is a separate guarantee.
    """
    forwarded = forwarded_client_headers(
        {
            "user-agent": "claude-cli/2.0.0",
            "x-stainless-timeout": "600",
            "x-claude-code-session-id": "abc",
        }
    )
    assert forwarded == {
        "user-agent": "claude-cli/2.0.0",
        "x-stainless-timeout": "600",
        "x-claude-code-session-id": "abc",
    }


def test_a_translated_request_forwards_nothing_of_the_clients() -> None:
    """`message-format-reshape.md` gives the translation path a whitelist and leaves it empty.

    The header the client negotiated is about the Anthropic wire format; the request that answers is a Responses one. Until this ruling the Anthropic-to-Responses leg forwarded `anthropic-beta` to an endpoint that has no betas.
    """
    client = {
        "anthropic-beta": "context-management-2025-06-27",
        "anthropic-version": "2023-06-01",
        "x-stainless-timeout": "600",
    }
    assert apply_path_header_policy(client, translated=True) == {}
    assert apply_path_header_policy(client, translated=False) == client


def test_header_names_are_matched_regardless_of_case() -> None:
    assert forwarded_client_headers({"Anthropic-Beta": "x"}) == {"anthropic-beta": "x"}


def test_build_context_carries_the_forwarded_headers() -> None:
    route = next(route for route in ROUTES if route.path == "/v1/messages")

    context = build_context(
        route,
        {"model": "claude-opus-5", "messages": []},
        {"anthropic-beta": "context-management-2025-06-27", "authorization": "Bearer secret"},
    )

    assert context.client_headers == {"anthropic-beta": "context-management-2025-06-27"}


def test_build_context_without_headers_carries_nothing() -> None:
    route = next(route for route in ROUTES if route.path == "/v1/messages")
    assert build_context(route, {"model": "claude-opus-5", "messages": []}).client_headers == {}


# What the example config configures, verbatim, and the model it configures it for.
SONNET_46_DENIED = compile_beta_flag_denials(
    {
        "claude-sonnet-4.6": [
            "interleaved-thinking-2025-05-14",
            "context-management-2025-06-27",
            "prompt-caching-scope-2026-01-05",
            "mid-conversation-system-2026-04-07",
        ]
    }
)


def test_only_the_flags_named_for_this_model_are_removed() -> None:
    """The whole point: the header travels, minus the flags this model answers 400 over."""
    headers, removed = strip_denied_beta_flags(
        {
            "anthropic-beta": "interleaved-thinking-2025-05-14,fine-grained-tool-streaming-2025-05-14,context-management-2025-06-27",
            "anthropic-version": "2023-06-01",
        },
        model="claude-sonnet-4.6",
        denials=SONNET_46_DENIED,
    )

    assert headers["anthropic-beta"] == "fine-grained-tool-streaming-2025-05-14"
    assert headers["anthropic-version"] == "2023-06-01"
    assert removed == (
        "interleaved-thinking-2025-05-14",
        "context-management-2025-06-27",
    )


def test_another_model_keeps_everything() -> None:
    """A flag is refused by a model, not by the proxy. An unconfigured model is not touched."""
    value = "interleaved-thinking-2025-05-14,context-management-2025-06-27"
    headers, removed = strip_denied_beta_flags(
        {"anthropic-beta": value},
        model="claude-opus-5",
        denials=SONNET_46_DENIED,
    )

    assert headers == {"anthropic-beta": value}
    assert removed == ()


def test_a_key_is_a_regex_so_a_dot_is_a_wildcard() -> None:
    """`claude-sonnet-4.6` also claims `claude-sonnet-4-6`, which here is wanted and still an accident.

    The two spellings are one model under this config's own conventions, so the wildcard lands where a folding rule would have. It is worth pinning precisely because it is not a folding rule: nothing here folds `.` to `-`, and an operator who wants only the literal id writes `claude-sonnet-4\\.6`.
    """
    headers, removed = strip_denied_beta_flags(
        {"anthropic-beta": "context-management-2025-06-27"},
        model="claude-sonnet-4-6",
        denials=SONNET_46_DENIED,
    )
    assert headers == {}
    assert removed == ("context-management-2025-06-27",)


def test_a_key_is_case_sensitive_unless_the_operator_says_otherwise() -> None:
    """A regex means regex semantics, including this one. `(?i)` is how an operator opts out."""
    value = "context-management-2025-06-27"
    headers, removed = strip_denied_beta_flags(
        {"anthropic-beta": value}, model="Claude-Sonnet-4.6", denials=SONNET_46_DENIED
    )
    assert headers == {"anthropic-beta": value}
    assert removed == ()

    insensitive = compile_beta_flag_denials({"(?i)claude-sonnet-4\\.6": [value]})
    headers, removed = strip_denied_beta_flags(
        {"anthropic-beta": value}, model="Claude-Sonnet-4.6", denials=insensitive
    )
    assert headers == {}
    assert removed == (value,)


def test_a_key_does_not_claim_a_longer_id_that_starts_with_it() -> None:
    """`fullmatch`, not `search`: a list of model ids must not silently widen to a family."""
    value = "context-management-2025-06-27"
    headers, removed = strip_denied_beta_flags(
        {"anthropic-beta": value},
        model="claude-sonnet-4.6-experimental",
        denials=SONNET_46_DENIED,
    )
    assert headers == {"anthropic-beta": value}
    assert removed == ()


def test_a_header_with_nothing_left_is_dropped_rather_than_sent_empty() -> None:
    """`anthropic-beta:` with an empty value is a third state neither side has a meaning for."""
    headers, _ = strip_denied_beta_flags(
        {"anthropic-beta": "context-management-2025-06-27", "anthropic-version": "2023-06-01"},
        model="claude-sonnet-4.6",
        denials=SONNET_46_DENIED,
    )
    assert headers == {"anthropic-version": "2023-06-01"}


def test_surrounding_whitespace_does_not_hide_a_flag() -> None:
    """`a, b` is as legal a header value as `a,b`, and the kept flags keep their own spelling."""
    headers, removed = strip_denied_beta_flags(
        {"anthropic-beta": " context-management-2025-06-27 , effort-2025-11-24 "},
        model="claude-sonnet-4.6",
        denials=SONNET_46_DENIED,
    )
    assert headers == {"anthropic-beta": "effort-2025-11-24"}
    assert removed == ("context-management-2025-06-27",)


def test_an_empty_map_is_the_identity() -> None:
    """The default. Nothing configured must mean nothing changed, header value included."""
    original = {"anthropic-beta": "context-management-2025-06-27"}
    headers, removed = strip_denied_beta_flags(
        original, model="claude-sonnet-4.6", denials=()
    )
    assert headers == original
    assert removed == ()


def test_the_callers_mapping_is_not_mutated() -> None:
    """A caller holding the client's headers for any other purpose still has what arrived."""
    original = {"anthropic-beta": "context-management-2025-06-27,effort-2025-11-24"}
    strip_denied_beta_flags(
        original, model="claude-sonnet-4.6", denials=SONNET_46_DENIED
    )
    assert original == {
        "anthropic-beta": "context-management-2025-06-27,effort-2025-11-24"
    }


def test_a_request_without_the_header_is_left_alone() -> None:
    headers, removed = strip_denied_beta_flags(
        {"anthropic-version": "2023-06-01"},
        model="claude-sonnet-4.6",
        denials=SONNET_46_DENIED,
    )
    assert headers == {"anthropic-version": "2023-06-01"}
    assert removed == ()


def test_the_first_matching_entry_wins_and_the_rest_are_not_consulted() -> None:
    """Ordered, so a narrow entry above a broad one is how an operator says which they meant.

    Under a union the narrow entry could only ever *add* to what the broad one takes away; first-match-wins is what lets it take away less.
    """
    denials = compile_beta_flag_denials(
        {
            "claude-sonnet-4.6": ["flag-a"],
            "claude-sonnet-.*": ["flag-a", "flag-b"],
        }
    )
    headers, removed = strip_denied_beta_flags(
        {"anthropic-beta": "flag-a,flag-b"}, model="claude-sonnet-4.6", denials=denials
    )
    assert headers == {"anthropic-beta": "flag-b"}
    assert removed == ("flag-a",)

    # The same table, for a model only the broad entry claims.
    headers, removed = strip_denied_beta_flags(
        {"anthropic-beta": "flag-a,flag-b"}, model="claude-sonnet-9", denials=denials
    )
    assert headers == {}
    assert set(removed) == {"flag-a", "flag-b"}


def test_a_key_that_is_not_a_valid_regex_fails_where_the_config_is_read() -> None:
    """At start-up, naming the key. `re`'s own message gives a character offset and no key."""
    try:
        compile_beta_flag_denials({"claude-sonnet-4.6": [], "opus-[": ["flag-a"]})
    except ValueError as error:
        assert "opus-[" in str(error)
    else:
        raise AssertionError("an unparseable key must not be accepted")


def test_a_flag_is_matched_regardless_of_case_and_reported_as_configured() -> None:
    """The name that comes back labels a metric, so it must be the operator's, not the client's.

    A client-controlled string in a Prometheus label has no bound on its series count: three spellings of one flag would be three series that never merge.
    """
    headers, removed = strip_denied_beta_flags(
        {"anthropic-beta": "Context-Management-2025-06-27"},
        model="claude-sonnet-4.6",
        denials=SONNET_46_DENIED,
    )
    assert headers == {}
    assert removed == ("context-management-2025-06-27",)


def test_a_repeated_flag_is_reported_once() -> None:
    """Both copies are removed; the metric hears about the flag once."""
    headers, removed = strip_denied_beta_flags(
        {"anthropic-beta": "context-management-2025-06-27,context-management-2025-06-27"},
        model="claude-sonnet-4.6",
        denials=SONNET_46_DENIED,
    )
    assert headers == {}
    assert removed == ("context-management-2025-06-27",)


def test_a_configured_model_whose_flags_all_miss_keeps_the_value_byte_for_byte() -> None:
    """Not a re-joined equivalent of it. Nothing was taken away, so nothing may look different.

    Distinct from the empty-map case: here the model *is* configured and the lookup *did* run — it is the early return after the scan that this pins.
    """
    original = {"anthropic-beta": " effort-2025-11-24 ,  fine-grained-tool-streaming-2025-05-14"}
    headers, removed = strip_denied_beta_flags(
        original, model="claude-sonnet-4.6", denials=SONNET_46_DENIED
    )
    assert headers == original
    assert removed == ()


def test_a_null_edits_list_becomes_empty() -> None:
    """The exact body Claude Code sends. Upstream refuses the `null` and accepts the `[]`."""
    payload: dict[str, Any] = {"context_management": {"edits": None}}
    normalize_context_management(payload)
    assert payload["context_management"] == {"edits": []}


def test_real_edits_are_left_alone() -> None:
    """Only the null sentinel is rewritten; a client asking for context editing still gets it."""
    edits = [{"type": "clear_tool_uses_20250919", "trigger": {"type": "input_tokens"}}]
    payload: dict[str, Any] = {"context_management": {"edits": edits}}
    normalize_context_management(payload)
    assert payload["context_management"]["edits"] == edits


def test_a_body_without_context_management_is_untouched() -> None:
    payload: dict[str, Any] = {"messages": []}
    normalize_context_management(payload)
    assert payload == {"messages": []}


def test_normalisation_happens_even_when_there_are_no_messages() -> None:
    """`fix_anthropic_request` returns early on a body with no message list.

    `context_management` is a top-level field and survives that shape, so running the two in the wrong order would leave the production body unfixed while every messages-based test stayed green.
    """
    payload: dict[str, Any] = {"context_management": {"edits": None}}
    fix_anthropic_request(payload, FixAnthropicRequestHook())
    assert payload["context_management"] == {"edits": []}


def test_the_flag_the_gateway_refuses_is_removed_and_the_rest_travel() -> None:
    """The measured failure: one unknown name kills a set that is otherwise fine.

    Sent as the client sends it — the whole negotiated header, with the refused flag in the middle. Upstream names only the bad one and refuses the request whole, so the repair has to remove that flag and leave the other twelve exactly as spelled.
    """
    headers, removed = strip_gateway_unsupported_betas(
        {
            "anthropic-beta": "claude-code-20250219,tool-search-tool-2025-10-19,context-management-2025-06-27",
            "anthropic-version": "2023-06-01",
        }
    )

    assert headers["anthropic-beta"] == "claude-code-20250219,context-management-2025-06-27"
    assert headers["anthropic-version"] == "2023-06-01"
    assert removed == ("tool-search-tool-2025-10-19",)


def test_the_accepted_neighbour_one_digit_away_is_not_removed() -> None:
    """`tool-search-tool-2025-11-19` is accepted by the same gateway that refuses `…-10-19`.

    The negative control on the list, and not a hypothetical: the two differ by one digit, so a repair written as a prefix or substring match would take the working one away with the broken one. Measured 2026-08-24, both.
    """
    value = "tool-search-tool-2025-11-19,advanced-tool-use-2025-11-20"
    headers, removed = strip_gateway_unsupported_betas({"anthropic-beta": value})

    assert headers == {"anthropic-beta": value}
    assert removed == ()


class _DescribingProvider:
    """Enough of a provider for routing to resolve a model; nothing here ever sends."""

    name = "ghc"

    @property
    def available_ids(self) -> frozenset[str]:
        return frozenset({"claude-sonnet-5"})

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
        if model_id != "claude-sonnet-5":
            return None
        return ModelDescriptor(
            id="claude-sonnet-5",
            endpoints=frozenset({ModelEndpoint.ANTHROPIC_MESSAGES}),
            adaptive_thinking=True,
        )

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
        # `shape_request` stops before any attempt, so reaching this means the test under it grew a leg it did not mean to have.
        raise AssertionError("this test shapes a request; it never sends one")

    async def count_tokens(self, payload: Any, *, model_id: str) -> httpx2.Response:
        raise AssertionError("this test shapes a request; it never counts one")


def test_the_driver_strips_the_gateway_flag_with_no_table_configured() -> None:
    """The one here that fails if nobody wired the gateway strip into the request path.

    Deliberately configured with **no** `strip_anthropic_beta_flags` at all, because that is the shape of the machine the failure was reported from and because it is what separates the two mechanisms: if this passed only when a table existed, the built-in list would be decoration on top of the operator's table rather than a layer of its own.

    Asserted through `shape_request` rather than by calling the strip, for the reason the subscriber tests give: being written is not being called.
    """
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "ghc",
            "model_providers": {"ghc": {"type": "github_copilot"}},
            "model_mappings": {"claude-sonnet-4-5": "claude-sonnet-5"},
        }
    )
    chain = build_chain(
        config, http_client=httpx2.AsyncClient(), providers={"ghc": _DescribingProvider()}
    )
    context = RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="claude-sonnet-4-5",
        payload={"model": "claude-sonnet-4-5", "max_tokens": 16, "messages": []},
        client_headers={
            "anthropic-beta": "claude-code-20250219,tool-search-tool-2025-10-19",
        },
    )

    shape_request(chain, context)

    assert context.client_headers["anthropic-beta"] == "claude-code-20250219"


def test_a_header_left_with_nothing_is_dropped_rather_than_sent_blank() -> None:
    """`anthropic-beta:` with an empty value is a third state neither side has a meaning for."""
    headers, removed = strip_gateway_unsupported_betas(
        {"anthropic-beta": "tool-search-tool-2025-10-19", "anthropic-version": "2023-06-01"}
    )

    assert "anthropic-beta" not in headers
    assert headers == {"anthropic-version": "2023-06-01"}
    assert removed == ("tool-search-tool-2025-10-19",)


def test_a_request_with_no_beta_header_is_untouched() -> None:
    headers, removed = strip_gateway_unsupported_betas({"anthropic-version": "2023-06-01"})

    assert headers == {"anthropic-version": "2023-06-01"}
    assert removed == ()


def test_both_strips_compose_on_one_header() -> None:
    """A request can carry a name the gateway never heard of *and* a capability this model lacks.

    The two answer different questions and neither subsumes the other, so this pins that running both leaves only the flags that survive both — the shape the driver actually applies.
    """
    after_gateway, gateway_removed = strip_gateway_unsupported_betas(
        {
            "anthropic-beta": "tool-search-tool-2025-10-19,interleaved-thinking-2025-05-14,fine-grained-tool-streaming-2025-05-14"
        }
    )
    final, model_removed = strip_denied_beta_flags(
        after_gateway, model="claude-sonnet-4.6", denials=SONNET_46_DENIED
    )

    assert gateway_removed == ("tool-search-tool-2025-10-19",)
    assert model_removed == ("interleaved-thinking-2025-05-14",)
    assert final["anthropic-beta"] == "fine-grained-tool-streaming-2025-05-14"


def test_every_flag_in_the_built_in_list_is_actually_stripped() -> None:
    """Each member asserted on its own, because the list is the whole feature.

    Removing an entry from `GATEWAY_UNSUPPORTED_BETAS` used to leave every test green — the other cases all happen to use `tool-search-tool-2025-10-19` — while a client sending the dropped flag went back to the measured gateway 400. Iterating the tuple keeps a future addition covered without anyone remembering to write a case for it.
    """
    assert GATEWAY_UNSUPPORTED_BETAS, "an empty list would make every assertion below vacuous"
    for flag in GATEWAY_UNSUPPORTED_BETAS:
        headers, removed = strip_gateway_unsupported_betas(
            {"anthropic-beta": f"claude-code-20250219,{flag}"}
        )
        assert removed == (flag,), flag
        assert headers["anthropic-beta"] == "claude-code-20250219", flag
