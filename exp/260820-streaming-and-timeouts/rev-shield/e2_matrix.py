"""Primitive-level comparison: wait_for(shield(task), t) vs wait({task}, timeout=t)."""
import asyncio, contextlib

async def pull(delay, outcome="value"):
    await asyncio.sleep(delay)
    if isinstance(outcome, BaseException):
        raise outcome
    return outcome

async def old_step(task, timeout):
    """Returns ('done', value) | ('timeout', None); raises what the task raises."""
    try:
        return ("done", await asyncio.wait_for(asyncio.shield(task), timeout=timeout))
    except TimeoutError:
        return ("timeout", None)

async def new_step(task, timeout):
    await asyncio.wait({task}, timeout=timeout)
    if task.done():
        return ("done", task.result())
    return ("timeout", None)

async def probe(step, name):
    loop = asyncio.get_running_loop()
    seen = []
    loop.set_exception_handler(lambda l, ctx: seen.append(ctx.get("message")))
    out = {}

    # (a) timeout=None, task finishes later
    t = asyncio.ensure_future(pull(0.05))
    out["a_none"] = await step(t, None)

    # (b) timeout=0.0, task pending -> must not busy-return without yielding, must not cancel task
    t = asyncio.ensure_future(pull(0.10))
    await asyncio.sleep(0)  # let it start
    r = await step(t, 0.0)
    out["b_zero"] = (r, "task_cancelled" if t.cancelled() else "task_alive", t.done())
    out["b_zero_then"] = await step(t, 1.0)

    # (c) task already done on entry
    t = asyncio.ensure_future(pull(0.0))
    await asyncio.sleep(0.02)
    assert t.done()
    ticks = 0
    async def counter():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0)
    c = asyncio.ensure_future(counter())
    out["c_done"] = await step(t, 1.0)
    c.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await c
    out["c_loop_ticks_while_waiting"] = ticks

    # (e) task cancelled externally while waiting
    t = asyncio.ensure_future(pull(5.0))
    await asyncio.sleep(0)
    loop.call_later(0.02, t.cancel)
    try:
        out["e_cancel"] = await step(t, 1.0)
    except asyncio.CancelledError:
        out["e_cancel"] = "CancelledError raised"
    except BaseException as exc:
        out["e_cancel"] = f"{type(exc).__name__} raised"

    # (f) task raises an ordinary exception
    t = asyncio.ensure_future(pull(0.02, ValueError("boom")))
    try:
        out["f_exc"] = await step(t, 1.0)
    except BaseException as exc:
        out["f_exc"] = f"{type(exc).__name__}({exc}) raised"

    # (f2) task raises StopAsyncIteration after having timed out once
    t = asyncio.ensure_future(pull(0.10, StopAsyncIteration()))
    await step(t, 0.02)
    try:
        out["f2_sai_after_timeout"] = await step(t, 1.0)
    except BaseException as exc:
        out["f2_sai_after_timeout"] = f"{type(exc).__name__} raised"
    with contextlib.suppress(BaseException):
        t.exception()
    await asyncio.sleep(0)
    out["handler_messages"] = seen
    print(f"== {name}")
    for k, v in out.items():
        print(f"   {k}: {v}")

async def main():
    await probe(old_step, "OLD wait_for(shield(task))")
    await probe(new_step, "NEW wait({task})")

asyncio.run(main())
