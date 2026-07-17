import importlib
from collections.abc import Callable
from types import ModuleType
from typing import cast

from app.config.settings import AppSettings
from app.hooks.registry import HookRegistryBuilder

type RegisterFunction = Callable[[HookRegistryBuilder, AppSettings], None]


def load_user_hook_modules(
    builder: HookRegistryBuilder,
    settings: AppSettings,
) -> tuple[str, ...]:
    loaded: list[str] = []
    for module_name in settings.hooks.modules:
        module: ModuleType = importlib.import_module(module_name)
        register = getattr(module, "register", None)
        if not callable(register):
            raise TypeError(f"hook module {module_name!r} must export register(builder, settings)")
        cast(RegisterFunction, register)(builder, settings)
        loaded.append(module_name)
    return tuple(loaded)
