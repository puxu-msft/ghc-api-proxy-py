import copy
import warnings
from collections.abc import Mapping
from typing import Any, cast


def _migrate_key(
    section: dict[str, Any],
    old_key: str,
    new_keys: tuple[str, ...],
    *,
    section_name: str,
) -> None:
    if old_key not in section:
        return

    old_value = section.pop(old_key)
    warnings.warn(
        f"{section_name}.{old_key} is deprecated; use "
        f"{', '.join(f'{section_name}.{key}' for key in new_keys)}",
        DeprecationWarning,
        stacklevel=3,
    )
    for new_key in new_keys:
        section.setdefault(new_key, old_value)


def migrate_compat(config: Mapping[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(dict(config))

    history = migrated.get("history")
    if isinstance(history, dict):
        _migrate_key(
            cast(dict[str, Any], history),
            "limit",
            ("success_limit", "failure_limit"),
            section_name="history",
        )

    timeouts = migrated.get("timeouts")
    if isinstance(timeouts, dict):
        typed_timeouts = cast(dict[str, Any], timeouts)
        _migrate_key(
            typed_timeouts,
            "stream_idle_timeout",
            ("stream_idle",),
            section_name="timeouts",
        )
        _migrate_key(
            typed_timeouts,
            "fetch_timeout",
            ("response_header",),
            section_name="timeouts",
        )

    return migrated
