"""The gate in front of the phase machine.

Kept apart from `phases` because it answers a different question: `phases` decides what this
generation is willing to do, and this decides what an arriving request is told when the answer
is no. Health probes go through regardless — a generation that stops answering them looks dead
to the thing that is trying to replace it.
"""

from __future__ import annotations

from uvicorn._types import ASGI3Application, ASGIReceiveCallable, ASGISendCallable, Scope

from app.lifecycle.rolling.generation.phases import GenerationLifecycle


class GenerationAdmissionMiddleware:
    _HEALTH_PATHS = frozenset({"/health/liveness", "/health/readiness", "/health"})

    def __init__(self, app: ASGI3Application, lifecycle: GenerationLifecycle) -> None:
        self._app = app
        self._lifecycle = lifecycle

    async def __call__(
        self,
        scope: Scope,
        receive: ASGIReceiveCallable,
        send: ASGISendCallable,
    ) -> None:
        scope_type = scope["type"]
        if scope_type == "lifespan":
            await self._app(scope, receive, send)
            return
        path = scope.get("path", "")
        if scope_type == "http" and path in self._HEALTH_PATHS:
            await self._app(scope, receive, send)
            return
        async with self._lifecycle.try_admit() as admitted:
            if admitted:
                await self._app(scope, receive, send)
                return
            if scope_type == "http":
                await send(
                    {
                        "type": "http.response.start",
                        "status": 503,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"connection", b"close"),
                        ],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b'{"error":{"type":"server_restarting"}}',
                    }
                )
                return
            if scope_type == "websocket":
                event = await receive()
                if event["type"] == "websocket.connect":
                    await send({"type": "websocket.accept"})
                    await send(
                        {
                            "type": "websocket.close",
                            "code": 1012,
                            "reason": "server_restarting",
                        }
                    )
                return
