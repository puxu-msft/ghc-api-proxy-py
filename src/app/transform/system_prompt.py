import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SystemPromptRules:
    prepend: tuple[str, ...] = ()
    append: tuple[str, ...] = ()
    replacements: tuple[tuple[str, str], ...] = ()


def apply_system_prompt_rules(
    messages: Sequence[Mapping[str, object]],
    rules: SystemPromptRules,
) -> list[dict[str, object]]:
    result = [copy.deepcopy(dict(message)) for message in messages]
    system_index = next(
        (index for index, message in enumerate(result) if message.get("role") == "system"),
        None,
    )
    content = ""
    if system_index is not None:
        raw_content = result[system_index].get("content")
        content = raw_content if isinstance(raw_content, str) else ""
    for old, new in rules.replacements:
        content = content.replace(old, new)
    parts = [*rules.prepend, content, *rules.append]
    combined = "\n".join(part for part in parts if part)
    if not combined:
        return result
    if system_index is None:
        result.insert(0, {"role": "system", "content": combined})
    else:
        result[system_index]["content"] = combined
    return result
