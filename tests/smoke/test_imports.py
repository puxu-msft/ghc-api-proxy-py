from importlib import import_module

import pytest

CORE_MODULES = (
    "aiofiles",
    "anthropic",
    "anyio",
    "fastapi",
    "httpx",
    "httpx_ws",
    "openai",
    "opentelemetry.instrumentation.fastapi",
    "opentelemetry.instrumentation.httpx",
    "opentelemetry.sdk",
    "orjson",
    "platformdirs",
    "pydantic",
    "pydantic_settings",
    "structlog",
    "textual",
    "tiktoken",
    "typer",
    "uvicorn",
)


@pytest.mark.parametrize("module_name", CORE_MODULES)
def test_core_dependency_imports(module_name: str) -> None:
    assert import_module(module_name) is not None
