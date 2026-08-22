"""What the client's headers and `context_management` look like by the time upstream sees them.

Both cover the same defect from opposite ends. Claude Code sends `anthropic-beta` with ten tokens
and `context_management: {"edits": null}` on every request; the chain forwarded neither correctly,
so upstream refused a field the beta would have enabled and the client saw a 502. Measured against
the live upstream on 2026-08-18: `{"edits": null}` is refused, `{"edits": []}` is accepted, and
without the beta header the field is not recognised at all.
"""

from typing import Any

from app.config.schema import FixAnthropicRequestHook
from app.pipeline.anthropic_request_hook import fix_anthropic_request, normalize_context_management
from app.pipeline.request_headers import forwarded_client_headers, strip_denied_beta_flags
from app.server.inbound import ROUTES, build_context


def test_the_beta_header_is_forwarded() -> None:
    """The one that decides whether a real request works at all."""
    forwarded = forwarded_client_headers(
        {"anthropic-beta": "context-management-2025-06-27,effort-2025-11-24"}
    )
    assert forwarded == {"anthropic-beta": "context-management-2025-06-27,effort-2025-11-24"}


def test_identity_and_credential_headers_are_not_forwarded() -> None:
    """Upstream is addressed as Copilot Chat, so the client's identity must not replace it.

    `authorization` is the credential case and `user-agent` the identity one; forwarding either
    would break the request rather than merely leak something, and the allowlist is what stops
    both without anyone having to enumerate them.
    """
    forwarded = forwarded_client_headers(
        {
            "authorization": "Bearer client-secret",
            "user-agent": "claude-cli/2.0.0",
            "x-stainless-timeout": "600",
            "x-claude-code-session-id": "abc",
            "anthropic-beta": "context-management-2025-06-27",
        }
    )
    assert forwarded == {"anthropic-beta": "context-management-2025-06-27"}


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
SONNET_46_DENIED = {
    "claude-sonnet-4.6": [
        "interleaved-thinking-2025-05-14",
        "context-management-2025-06-27",
        "prompt-caching-scope-2026-01-05",
        "mid-conversation-system-2026-04-07",
    ]
}


def test_only_the_flags_named_for_this_model_are_removed() -> None:
    """The whole point: the header travels, minus the flags this model answers 400 over."""
    headers, removed = strip_denied_beta_flags(
        {
            "anthropic-beta": "interleaved-thinking-2025-05-14,fine-grained-tool-streaming-2025-05-14,context-management-2025-06-27",
            "anthropic-version": "2023-06-01",
        },
        models=("claude-sonnet-4.6",),
        denied_by_model=SONNET_46_DENIED,
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
        models=("claude-opus-5",),
        denied_by_model=SONNET_46_DENIED,
    )

    assert headers == {"anthropic-beta": value}
    assert removed == ()


def test_the_model_key_folds_the_way_model_mappings_does() -> None:
    """The operator writes `claude-sonnet-4.6`; what arrives is whatever the route resolved to.

    Exact string equality would leave the one spelling the example config uses silently inert — the failure mode of a strip that never fires is a 400 nobody can trace back to this map.
    """
    for resolved in ("claude-sonnet-4-6", "Claude-Sonnet-4.6"):
        headers, removed = strip_denied_beta_flags(
            {"anthropic-beta": "context-management-2025-06-27"},
            models=(resolved,),
            denied_by_model=SONNET_46_DENIED,
        )
        assert headers == {}, resolved
        assert removed == ("context-management-2025-06-27",), resolved


def test_a_header_with_nothing_left_is_dropped_rather_than_sent_empty() -> None:
    """`anthropic-beta:` with an empty value is a third state neither side has a meaning for."""
    headers, _ = strip_denied_beta_flags(
        {"anthropic-beta": "context-management-2025-06-27", "anthropic-version": "2023-06-01"},
        models=("claude-sonnet-4.6",),
        denied_by_model=SONNET_46_DENIED,
    )
    assert headers == {"anthropic-version": "2023-06-01"}


def test_surrounding_whitespace_does_not_hide_a_flag() -> None:
    """`a, b` is as legal a header value as `a,b`, and the kept flags keep their own spelling."""
    headers, removed = strip_denied_beta_flags(
        {"anthropic-beta": " context-management-2025-06-27 , effort-2025-11-24 "},
        models=("claude-sonnet-4.6",),
        denied_by_model=SONNET_46_DENIED,
    )
    assert headers == {"anthropic-beta": "effort-2025-11-24"}
    assert removed == ("context-management-2025-06-27",)


def test_an_empty_map_is_the_identity() -> None:
    """The default. Nothing configured must mean nothing changed, header value included."""
    original = {"anthropic-beta": "context-management-2025-06-27"}
    headers, removed = strip_denied_beta_flags(
        original, models=("claude-sonnet-4.6",), denied_by_model={}
    )
    assert headers == original
    assert removed == ()


def test_the_callers_mapping_is_not_mutated() -> None:
    """A caller holding the client's headers for any other purpose still has what arrived."""
    original = {"anthropic-beta": "context-management-2025-06-27,effort-2025-11-24"}
    strip_denied_beta_flags(
        original, models=("claude-sonnet-4.6",), denied_by_model=SONNET_46_DENIED
    )
    assert original == {
        "anthropic-beta": "context-management-2025-06-27,effort-2025-11-24"
    }


def test_a_request_without_the_header_is_left_alone() -> None:
    headers, removed = strip_denied_beta_flags(
        {"anthropic-version": "2023-06-01"},
        models=("claude-sonnet-4.6",),
        denied_by_model=SONNET_46_DENIED,
    )
    assert headers == {"anthropic-version": "2023-06-01"}
    assert removed == ()


def test_an_entry_under_the_requested_alias_fires_for_the_model_it_maps_to() -> None:
    """The case the authoritative config is actually in, and the one that decides `models` is plural.

    `config.example.yaml` writes this table under `claude-sonnet-4.6` while `model_mappings` maps `claude-sonnet-4.6: claude-sonnet-5`, so no request ever *resolves* to the name the table is written under. Keyed on the resolved name alone, the operator's whole measured table is inert and nothing reports that it is.
    """
    headers, removed = strip_denied_beta_flags(
        {"anthropic-beta": "context-management-2025-06-27"},
        models=("claude-sonnet-4.6", "claude-sonnet-5"),
        denied_by_model=SONNET_46_DENIED,
    )
    assert headers == {}
    assert removed == ("context-management-2025-06-27",)


def test_an_entry_under_the_resolved_id_fires_for_a_client_that_asked_for_it_directly() -> None:
    """The other half of the union. A client naming the real id must be protected too."""
    headers, removed = strip_denied_beta_flags(
        {"anthropic-beta": "context-management-2025-06-27"},
        models=("some-alias", "claude-sonnet-4.6"),
        denied_by_model=SONNET_46_DENIED,
    )
    assert headers == {}
    assert removed == ("context-management-2025-06-27",)


def test_two_canonically_equal_keys_both_contribute() -> None:
    """`claude-sonnet-4.6` and `claude-sonnet-4-6` are one model; neither entry may be dropped.

    Taking the first match and returning made the flags under the second disappear with nothing saying so — the operator sees a key they wrote and a flag that still reaches upstream.
    """
    headers, removed = strip_denied_beta_flags(
        {"anthropic-beta": "flag-a,flag-b,flag-c"},
        models=("claude-sonnet-4.6",),
        denied_by_model={
            "claude-sonnet-4.6": ["flag-a"],
            "claude-sonnet-4-6": ["flag-b"],
        },
    )
    assert headers == {"anthropic-beta": "flag-c"}
    assert set(removed) == {"flag-a", "flag-b"}


def test_a_flag_is_matched_regardless_of_case_and_reported_as_configured() -> None:
    """The name that comes back labels a metric, so it must be the operator's, not the client's.

    A client-controlled string in a Prometheus label has no bound on its series count: three spellings of one flag would be three series that never merge.
    """
    headers, removed = strip_denied_beta_flags(
        {"anthropic-beta": "Context-Management-2025-06-27"},
        models=("claude-sonnet-4.6",),
        denied_by_model=SONNET_46_DENIED,
    )
    assert headers == {}
    assert removed == ("context-management-2025-06-27",)


def test_a_repeated_flag_is_reported_once() -> None:
    """Both copies are removed; the metric hears about the flag once."""
    headers, removed = strip_denied_beta_flags(
        {"anthropic-beta": "context-management-2025-06-27,context-management-2025-06-27"},
        models=("claude-sonnet-4.6",),
        denied_by_model=SONNET_46_DENIED,
    )
    assert headers == {}
    assert removed == ("context-management-2025-06-27",)


def test_a_configured_model_whose_flags_all_miss_keeps_the_value_byte_for_byte() -> None:
    """Not a re-joined equivalent of it. Nothing was taken away, so nothing may look different.

    Distinct from the empty-map case: here the model *is* configured and the lookup *did* run — it is the early return after the scan that this pins.
    """
    original = {"anthropic-beta": " effort-2025-11-24 ,  fine-grained-tool-streaming-2025-05-14"}
    headers, removed = strip_denied_beta_flags(
        original, models=("claude-sonnet-4.6",), denied_by_model=SONNET_46_DENIED
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

    `context_management` is a top-level field and survives that shape, so running the two in the
    wrong order would leave the production body unfixed while every messages-based test stayed
    green.
    """
    payload: dict[str, Any] = {"context_management": {"edits": None}}
    fix_anthropic_request(payload, FixAnthropicRequestHook())
    assert payload["context_management"] == {"edits": []}
