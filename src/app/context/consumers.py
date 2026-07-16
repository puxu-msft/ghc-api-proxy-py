from typing import Any, Protocol

from app.pipeline.context import RequestContext


class ContextConsumer(Protocol):
    async def handle(
        self,
        event: str,
        context: RequestContext,
        data: dict[str, Any],
    ) -> None: ...


class ContextEventBus:
    def __init__(self) -> None:
        self._consumers: list[ContextConsumer] = []

    def subscribe(self, consumer: ContextConsumer) -> None:
        self._consumers.append(consumer)

    async def publish(
        self,
        event: str,
        context: RequestContext,
        data: dict[str, Any],
    ) -> None:
        for consumer in self._consumers:
            await consumer.handle(event, context, data)