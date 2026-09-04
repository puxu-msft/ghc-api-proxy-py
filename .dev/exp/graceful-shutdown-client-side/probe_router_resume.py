"""The reviewer's state trace for the `both`-mode quiesce -> drain -> resume cycle.

Before the fix the router's own `_arm_locked` only set the inner adapter's event and never cleared
its refusal, so every request after a resume answered 503 forever on a listener that was accepting
normally. Reads the private fields directly, because the question is exactly what they hold.
"""

from __future__ import annotations

import asyncio
import socket
from pathlib import Path

from fastapi import FastAPI
from uvicorn import Config

from app.lifecycle.activation import ActivatedSocketSet, ExpectedListener
from app.lifecycle.adapter import UvicornListenerAdapter
from app.lifecycle.listener import FirstByteRoutingAdapter
from app.server.tls import build_server_ssl_context, generate_self_signed


def _app() -> FastAPI:
    app = FastAPI()

    async def live() -> dict[str, str]:
        return {"status": "ok"}

    app.add_api_route("/health/liveness", live)
    return app


async def main() -> int:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(32)
    port = listener.getsockname()[1]
    listeners = ActivatedSocketSet(
        {"http": listener},
        [ExpectedListener("http", socket.AF_INET, "127.0.0.1", port)],
    )
    material = generate_self_signed(Path("/tmp/ghc-resume-probe-tls"))
    inner = UvicornListenerAdapter(Config(_app(), log_config=None), listeners)
    router = FirstByteRoutingAdapter(inner, listeners, build_server_ssl_context(material))

    def state(label: str) -> None:
        refusal = inner._admission_refusal  # pyright: ignore[reportPrivateUsage]
        opened = inner._admission_open.is_set()  # pyright: ignore[reportPrivateUsage]
        print(f"{label:<12} refusal={refusal!r:<32} open={opened}", flush=True)

    await router.startup_lifespan()
    await router.register_dormant()
    await router.arm()
    state("armed:")
    await router.stop_accepting()
    state("quiesced:")
    asked = await router.stop_admitting()
    state(f"drained({asked}):")
    await router.resume_accepting()
    state("resumed:")

    refusal = inner._admission_refusal  # pyright: ignore[reportPrivateUsage]
    stuck = refusal is not None
    print(
        "VERDICT router: " + ("REFUSAL STUCK -> permanent 503 after resume" if stuck else "clean"),
        flush=True,
    )

    await router.stop_accepting()
    await router.shutdown_lifespan()
    await router.close_masters()
    listeners.close()
    return 1 if stuck else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
