import copy
import json
from dataclasses import dataclass
from typing import Any, cast

from app.anthropic.message_tools import preprocess_tools
from app.anthropic.sanitize.read_tool_result_tags import strip_read_tool_result_tags
from app.anthropic.thinking.destack import DestackStrategy, destack_content
from app.hooks.context import HookContext
from app.hooks.types import HookErrorMode, PayloadHookResult, PayloadPhase


@dataclass(frozen=True, slots=True)
class StripReadToolResultTagsHook:
    name: str = "builtin:strip_read_tool_result_tags"
    phase: PayloadPhase = PayloadPhase.POST_SANITIZE
    order: int = 100
    error_mode: HookErrorMode = HookErrorMode.FAIL_REQUEST

    async def run(
        self,
        payload: dict[str, Any],
        context: HookContext,
    ) -> PayloadHookResult:
        del context
        wire = copy.deepcopy(payload)
        changed = False
        for message in cast(list[dict[str, Any]], wire.get("messages", [])):
            content = message.get("content")
            if not isinstance(content, list):
                continue
            rewritten: list[object] = []
            for raw_block in cast(list[object], content):
                if not isinstance(raw_block, dict):
                    rewritten.append(raw_block)
                    continue
                block = cast(dict[str, Any], raw_block)
                cleaned = strip_read_tool_result_tags(block)
                changed = changed or cleaned != block
                rewritten.append(cleaned)
            message["content"] = rewritten
        return PayloadHookResult(
            wire,
            changed,
            ("strip_read_tool_result_tags",) if changed else (),
        )


@dataclass(frozen=True, slots=True)
class ThinkingDestackHook:
    strategy: DestackStrategy
    name: str = "builtin:thinking_destack"
    phase: PayloadPhase = PayloadPhase.POST_SANITIZE
    order: int = 200
    error_mode: HookErrorMode = HookErrorMode.FAIL_REQUEST

    async def run(
        self,
        payload: dict[str, Any],
        context: HookContext,
    ) -> PayloadHookResult:
        del context
        wire = copy.deepcopy(payload)
        changed = False
        for message in cast(list[dict[str, Any]], wire.get("messages", [])):
            content = message.get("content")
            if message.get("role") != "assistant" or not isinstance(content, list):
                continue
            rewritten, modified = destack_content(
                cast(list[dict[str, Any]], content),
                self.strategy,
            )
            message["content"] = rewritten
            changed = changed or modified
        return PayloadHookResult(
            wire,
            changed,
            ("thinking_destack",) if changed else (),
        )


@dataclass(frozen=True, slots=True)
class ToolPreprocessorHook:
    enabled: bool
    non_deferred: tuple[str, ...]
    name: str = "builtin:tool_preprocessor"
    phase: PayloadPhase = PayloadPhase.POST_SANITIZE
    order: int = 300
    error_mode: HookErrorMode = HookErrorMode.FAIL_REQUEST

    async def run(
        self,
        payload: dict[str, Any],
        context: HookContext,
    ) -> PayloadHookResult:
        del context
        wire = copy.deepcopy(payload)
        tools = wire.get("tools")
        if not isinstance(tools, list):
            return PayloadHookResult(wire)
        typed_tools = cast(list[dict[str, Any]], tools)
        rewritten = preprocess_tools(
            typed_tools,
            inject_tool_search=self.enabled,
            non_deferred=self.non_deferred,
        )
        changed = rewritten != typed_tools
        wire["tools"] = rewritten
        return PayloadHookResult(
            wire,
            changed,
            ("tool_preprocessor",) if changed else (),
        )


@dataclass(frozen=True, slots=True)
class DeduplicateToolCallsHook:
    name: str = "builtin:deduplicate_tool_calls"
    phase: PayloadPhase = PayloadPhase.POST_SANITIZE
    order: int = 400
    error_mode: HookErrorMode = HookErrorMode.FAIL_REQUEST

    async def run(
        self,
        payload: dict[str, Any],
        context: HookContext,
    ) -> PayloadHookResult:
        del context
        wire = copy.deepcopy(payload)
        messages = cast(list[dict[str, Any]], wire.get("messages", []))
        seen_signatures: set[str] = set()
        duplicate_ids: set[str] = set()
        changed = False
        for index, message in enumerate(messages[:-1]):
            next_message = messages[index + 1]
            if message.get("role") != "assistant" or next_message.get("role") != "user":
                continue
            assistant_content = message.get("content")
            user_content = next_message.get("content")
            if not isinstance(assistant_content, list) or not isinstance(user_content, list):
                continue
            result_by_id: dict[str, dict[str, Any]] = {}
            for raw_block in cast(list[object], user_content):
                if not isinstance(raw_block, dict):
                    continue
                block = cast(dict[str, Any], raw_block)
                tool_use_id = block.get("tool_use_id")
                if block.get("type") == "tool_result" and isinstance(tool_use_id, str):
                    result_by_id[tool_use_id] = block
            kept: list[object] = []
            for raw_block in cast(list[object], assistant_content):
                if not isinstance(raw_block, dict):
                    kept.append(raw_block)
                    continue
                block = cast(dict[str, Any], raw_block)
                if block.get("type") != "tool_use":
                    kept.append(block)
                    continue
                tool_id = block.get("id")
                result = result_by_id.get(str(tool_id))
                if not isinstance(tool_id, str) or result is None:
                    kept.append(block)
                    continue
                signature = json.dumps(
                    [block.get("name"), block.get("input"), result.get("content")],
                    sort_keys=True,
                    separators=(",", ":"),
                )
                if signature in seen_signatures:
                    duplicate_ids.add(tool_id)
                    changed = True
                    continue
                seen_signatures.add(signature)
                kept.append(block)
            message["content"] = kept
        if duplicate_ids:
            for message in messages:
                content = message.get("content")
                if not isinstance(content, list):
                    continue
                kept_content: list[object] = []
                for raw_block in cast(list[object], content):
                    kept_block: object = raw_block
                    if isinstance(raw_block, dict):
                        block = cast(dict[str, Any], raw_block)
                        if (
                            block.get("type") == "tool_result"
                            and block.get("tool_use_id") in duplicate_ids
                        ):
                            continue
                        kept_block = block
                    kept_content.append(kept_block)
                message["content"] = kept_content
        wire["messages"] = messages
        return PayloadHookResult(
            wire,
            changed,
            ("deduplicate_tool_calls",) if changed else (),
        )
