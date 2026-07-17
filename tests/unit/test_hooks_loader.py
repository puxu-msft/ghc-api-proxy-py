import sys
from types import ModuleType

import pytest

from app.config.settings import AppSettings
from app.hooks.loader import load_user_hook_modules
from app.hooks.registry import HookRegistryBuilder


def test_loader_calls_explicit_module_register() -> None:
    module_name = "test_user_hook_module"
    module = ModuleType(module_name)
    called: list[AppSettings] = []

    def register(builder: HookRegistryBuilder, settings: AppSettings) -> None:
        del builder
        called.append(settings)

    module.register = register  # type: ignore[attr-defined]
    sys.modules[module_name] = module
    settings = AppSettings.model_validate({"hooks": {"modules": [module_name]}})
    try:
        loaded = load_user_hook_modules(HookRegistryBuilder(), settings)
    finally:
        sys.modules.pop(module_name, None)

    assert loaded == (module_name,)
    assert called == [settings]


def test_loader_rejects_missing_register() -> None:
    module_name = "test_user_hook_without_register"
    sys.modules[module_name] = ModuleType(module_name)
    settings = AppSettings.model_validate({"hooks": {"modules": [module_name]}})
    try:
        with pytest.raises(TypeError, match="must export register"):
            load_user_hook_modules(HookRegistryBuilder(), settings)
    finally:
        sys.modules.pop(module_name, None)


def test_loader_surfaces_import_failure() -> None:
    settings = AppSettings.model_validate(
        {"hooks": {"modules": ["module_that_does_not_exist_123"]}}
    )

    with pytest.raises(ModuleNotFoundError):
        load_user_hook_modules(HookRegistryBuilder(), settings)
