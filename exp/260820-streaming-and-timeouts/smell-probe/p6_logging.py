"""Where does an asyncio loop-level exception report actually land once setup_logging has run,
and does it carry a stack?"""
import asyncio, logging, sys
from app.observability.logging import setup_logging

async def boom():
    raise RuntimeError("upstream pull blew up")

async def main():
    print("--- default handler installed?", asyncio.get_running_loop().get_exception_handler())
    t = asyncio.ensure_future(boom())
    await asyncio.sleep(0.05)
    del t
    import gc; gc.collect()
    await asyncio.sleep(0.05)
    print("--- asyncio logger:", logging.getLogger("asyncio").handlers,
          "propagate=", logging.getLogger("asyncio").propagate,
          "effective level=", logging.getLogger("asyncio").getEffectiveLevel())
    print("--- root handlers:", logging.getLogger().handlers)

for fmt in ("text", "json"):
    print(f"\n===================== log_format={fmt} =====================")
    setup_logging(log_format=fmt, log_level="INFO", colors=False)
    asyncio.run(main())
