from pathlib import Path
from typing import Any, cast

import pytest

from app.config.settings import AppSettings
from app.hooks.builtin import register_builtin_hooks
from app.hooks.context import HookContext
from app.hooks.registry import HookRegistryBuilder
from app.hooks.types import PayloadPhase
from app.tokenization.state_store import TokenizationStateStore


def _context() -> HookContext:
    return HookContext(
        request_id="request",
        endpoint="anthropic-messages",
        protocol="anthropic",
        original_model="model",
        resolved_model="model",
        session_id=None,
        agent_id=None,
        attempt_number=0,
        settings=AppSettings(),
    )


def _registry(tmp_path: Path, settings: AppSettings | None = None):
    resolved = settings or AppSettings()
    builder = HookRegistryBuilder(disabled=tuple(resolved.hooks.disabled))
    register_builtin_hooks(
        builder,
        resolved,
        quarantine=None,
        tokenization_state=TokenizationStateStore(tmp_path / "state.json"),
    )
    return builder.build()


@pytest.mark.asyncio
async def test_builtin_payload_hooks_preserve_unknowns_without_wire_tool_preparation(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    payload = {
        "model": "model",
        "future": {"keep": True},
        "tools": [{"name": "Read", "input_schema": {"type": "object"}, "future": 1}],
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "a"},
                    {"type": "thinking", "thinking": "b"},
                ],
            }
        ],
    }
    current = payload
    for hook in registry.for_phase(PayloadPhase.POST_SANITIZE):
        current = (await hook.run(current, _context())).payload

    assert current["future"] == {"keep": True}
    tools = cast(list[dict[str, Any]], current["tools"])
    messages = cast(list[dict[str, Any]], current["messages"])
    content = cast(list[dict[str, Any]], messages[0]["content"])
    assert tools[0]["future"] == 1
    assert "defer_loading" not in tools[0]
    assert len(tools) == 1
    assert [block["type"] for block in content] == [
        "thinking",
        "text",
        "thinking",
    ]


def test_tool_preprocessor_name_is_not_a_cross_protocol_payload_hook(tmp_path: Path) -> None:
    names = {
        hook.name for hook in _registry(tmp_path).for_phase(PayloadPhase.POST_SANITIZE)
    }

    assert "builtin:tool_preprocessor" not in names


def test_deduplicate_hook_is_disabled_by_default(tmp_path: Path) -> None:
    default_names = {
        hook.name for hook in _registry(tmp_path).for_phase(PayloadPhase.POST_SANITIZE)
    }
    enabled = AppSettings.model_validate(
        {"hooks": {"deduplicate_tool_calls": True}}
    )
    enabled_names = {
        hook.name
        for hook in _registry(tmp_path, enabled).for_phase(PayloadPhase.POST_SANITIZE)
    }

    assert "builtin:deduplicate_tool_calls" not in default_names
    assert "builtin:deduplicate_tool_calls" in enabled_names
