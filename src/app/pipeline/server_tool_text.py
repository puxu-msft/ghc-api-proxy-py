"""One text rendering for server-tool history on every upstream leg.

A conversation can move between providers. A server-tool block therefore has to flatten to the same text whether the next request targets Anthropic or Responses; two renderers make one history acquire two meanings without either endpoint reporting an error.

The renderer preserves readable facts and reports whether it dropped opaque content. `encrypted_content` is deliberately never put into model-visible text: it is meaningful only to the provider that issued it, but its removal is still a loss callers must record.
"""

from dataclasses import dataclass
from typing import Any, cast

from app.pipeline.anthropic_server_tools import project_web_search_action

WEB_SEARCH = "web_search"
WEB_FETCH = "web_fetch"


@dataclass(frozen=True, slots=True)
class ServerToolTextRendering:
    source_type: str
    text: str
    cache_control: Any = None
    has_cache_control: bool = False
    dropped_opaque: bool = False

    def as_text_block(self) -> dict[str, Any]:
        block: dict[str, Any] = {"type": "text", "text": self.text}
        if self.has_cache_control:
            block["cache_control"] = self.cache_control
        return block


def call_subject(raw_input: Any) -> str:
    """What a server-tool call was about, as a trailing fragment."""
    if not isinstance(raw_input, dict):
        return ""
    entry = cast(dict[str, Any], raw_input)
    for key in ("query", "url"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return f" {value.strip()}"
    return ""


def call_text(family: str, raw_input: Any) -> str:
    """The line that stands in for one server-tool call."""
    return f"[{family}]{call_subject(raw_input)}"


def web_search_call_text(action: Any) -> str:
    """Render a Responses hosted-search action without losing readable fields."""
    projected = project_web_search_action(action)
    suffix = f" {projected.readable}" if projected.readable else ""
    return f"[{WEB_SEARCH}]{suffix}"


def render_server_tool_block(
    block: Any,
    *,
    families: tuple[str, ...] | None = None,
) -> ServerToolTextRendering | None:
    """Render one Anthropic server-tool history block as replayable text.

    ``families`` limits a caller that owns only known-rejected families. With no
    limit, every server-tool family keeps the generic text fallback the
    Responses translator historically provided.
    """
    if not isinstance(block, dict):
        return None
    entry = cast(dict[str, Any], block)
    block_type = entry.get("type")
    if not isinstance(block_type, str):
        return None

    text: str
    dropped_opaque = False
    if block_type == "server_tool_use":
        name = entry.get("name")
        if not isinstance(name, str):
            return None
        family = _family(name, families)
        if family is None:
            return None
        text = call_text(family, entry.get("input"))
    else:
        if block_type == "tool_result" or not block_type.endswith("_tool_result"):
            return None
        family = _family(block_type[: -len("_tool_result")], families)
        if family is None:
            return None
        text, dropped_opaque = _render_results(entry.get("content"), family)

    return ServerToolTextRendering(
        source_type=block_type,
        text=text,
        cache_control=entry.get("cache_control"),
        has_cache_control="cache_control" in entry,
        dropped_opaque=dropped_opaque,
    )


def _family(name: str, families: tuple[str, ...] | None) -> str | None:
    if families is None:
        return name or None
    for family in families:
        if name.startswith(family):
            return family
    return None


def _describe_one(item: Any) -> tuple[str | None, bool]:
    if not isinstance(item, dict):
        return None, False
    result = cast(dict[str, Any], item)
    title = result.get("title")
    url = result.get("url")
    has_title = isinstance(title, str) and bool(title.strip())
    has_url = isinstance(url, str) and bool(url.strip())
    line: str | None = None
    if has_title and has_url:
        line = f"- {title} — {url}"
    elif has_url:
        line = f"- {url}"
    elif has_title:
        line = f"- {title}"
    return line, "encrypted_content" in result


def _failure_of(content: Any) -> str | None:
    if not isinstance(content, dict):
        return None
    entry = cast(dict[str, Any], content)
    kind = entry.get("type")
    code = entry.get("error_code")
    failed = (isinstance(kind, str) and kind.endswith("_error")) or code is not None
    if not failed:
        return None
    return code if isinstance(code, str) else ""


def _render_results(content: Any, family: str) -> tuple[str, bool]:
    failure = _failure_of(content)
    if failure is not None:
        text = f"[{family} failed: {failure}]" if failure else f"[{family} failed]"
        return text, False

    items: list[Any] = (
        cast(list[Any], content) if isinstance(content, list) else [content] if content else []
    )
    described = [_describe_one(item) for item in items]
    lines = [line for line, _ in described if line is not None]
    dropped_opaque = any(dropped for _, dropped in described)
    if not lines:
        return f"[{family} results omitted]", dropped_opaque
    return "\n".join([f"[{family} results]", *lines]), dropped_opaque


__all__ = [
    "WEB_FETCH",
    "WEB_SEARCH",
    "ServerToolTextRendering",
    "call_subject",
    "call_text",
    "render_server_tool_block",
    "web_search_call_text",
]
