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
from app.pipeline.request_headers import forwarded_client_headers
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
