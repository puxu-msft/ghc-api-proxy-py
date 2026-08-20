"""Keep-alive cue counting against the real _events_with_ping, plus a spin-rate probe."""
import asyncio, time
from app.pipeline.delivery.stream import _events_with_ping

async def silence_then_end(delay):
    await asyncio.sleep(delay)
    return
    yield b""

async def s1():
    n = [x async for x in _events_with_ping(silence_then_end(2.5), 1)]
    return f"S1 silence2.5s/interval1 -> yields={n}"

async def s2():
    async def feed():
        await asyncio.sleep(1.5)
        yield b"event: ping\ndata: {}\n\n"
        await asyncio.sleep(1.5)
    n = [x async for x in _events_with_ping(feed(), 1)]
    return f"S2 payload@1.5 end@3.0/interval1 -> yields={[type(x).__name__ for x in n]}"

async def s3():
    loop = asyncio.get_running_loop()
    started = asyncio.Event()          # deliberately never set
    deadline = loop.time() + 0.2
    count = 0
    t0 = time.perf_counter()
    agen = _events_with_ping(silence_then_end(1.2), 0,
                             response_headers_deadline=deadline, response_started=started)
    async for x in agen:
        count += 1
    return f"S3 unset-response_started spin -> nones={count} over {time.perf_counter()-t0:.2f}s"

async def main():
    for c in (s1(), s2(), s3()):
        print(await c)

asyncio.run(main())
