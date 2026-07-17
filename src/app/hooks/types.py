from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

from app.hooks.context import HookContext

if TYPE_CHECKING:
    from app.pipeline.strategies import RetryStrategy


class PayloadPhase(StrEnum):
    PRE_SANITIZE = "pre_sanitize"
    POST_SANITIZE = "post_sanitize"
    PRE_SEND = "pre_send"


class HookErrorMode(StrEnum):
    FAIL_REQUEST = "fail_request"
    CONTINUE = "continue"


class ObserverEvent(StrEnum):
    REQUEST_RECEIVED = "request_received"
    PRE_SANITIZE = "pre_sanitize"
    POST_SANITIZE = "post_sanitize"
    PRE_SEND = "pre_send"
    RESPONSE = "response"
    ERROR = "error"
    FINALIZE = "finalize"


@dataclass(frozen=True, slots=True)
class PayloadHookResult:
    payload: dict[str, Any]
    modified: bool = False
    modifications: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResponseHookResult:
    body: bytes
    modified: bool = False
    modifications: tuple[str, ...] = ()


class PayloadHook(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def phase(self) -> PayloadPhase: ...

    @property
    def order(self) -> int: ...

    @property
    def error_mode(self) -> HookErrorMode: ...

    async def run(
        self,
        payload: dict[str, Any],
        context: HookContext,
    ) -> PayloadHookResult: ...


class RetryStrategyFactory(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def order(self) -> int: ...

    def create(self, context: HookContext) -> RetryStrategy: ...


class ResponseHook(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def order(self) -> int: ...

    @property
    def error_mode(self) -> HookErrorMode: ...

    async def transform(
        self,
        body: bytes,
        status_code: int,
        context: HookContext,
    ) -> ResponseHookResult: ...


class ObserverHook(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def order(self) -> int: ...

    @property
    def events(self) -> frozenset[ObserverEvent]: ...

    async def observe(
        self,
        event: ObserverEvent,
        context: HookContext,
        data: Mapping[str, Any],
    ) -> None: ...
