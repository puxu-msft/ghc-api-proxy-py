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


def _drop_key(
    section: dict[str, Any],
    old_key: str,
    *,
    section_name: str,
) -> None:
    if old_key not in section:
        return

    section.pop(old_key)
    warnings.warn(
        f"{section_name}.{old_key} has been removed; raw capture is constrained "
        "by the per-file quota (max_file_bytes) only",
        DeprecationWarning,
        stacklevel=3,
    )


def migrate_compat(config: Mapping[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(dict(config))

    _migrate_key(
        migrated,
        "fallback_model_provider",
        ("default_model_provider",),
        section_name="root",
    )

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

    observability = migrated.get("observability")
    if isinstance(observability, dict):
        raw_capture = cast(dict[str, Any], observability).get("raw_capture")
        if isinstance(raw_capture, dict):
            _drop_key(
                cast(dict[str, Any], raw_capture),
                "max_total_bytes",
                section_name="observability.raw_capture",
            )

    return migrated
