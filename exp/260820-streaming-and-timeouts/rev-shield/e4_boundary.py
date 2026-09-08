"""The tie: the pull completes in the very loop iteration the timeout fires."""
import asyncio

async def old_step(task, timeout):
    try:
        return ("done", await asyncio.wait_for(asyncio.shield(task), timeout=timeout))
    except TimeoutError:
        return ("timeout", None)

async def new_step(task, timeout):
    await asyncio.wait({task}, timeout=timeout)
    if task.done():
        return ("done", task.result())
    return ("timeout", None)

async def trial(step, delay, timeout, order):
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    task = asyncio.ensure_future(asyncio.shield(fut))  # a task that finishes when fut does
    await asyncio.sleep(0)
    if order == "before":
        loop.call_later(delay, fut.set_result, "v")
        r = await step(task, timeout)
    else:
        h = asyncio.ensure_future(step(task, timeout))
        await asyncio.sleep(0)
        loop.call_later(delay, fut.set_result, "v")
        r = await h
    if not task.done():
        r2 = await step(task, 1.0)
    else:
        r2 = None
    return r, r2

async def main():
    for name, step in (("OLD", old_step), ("NEW", new_step)):
        for order in ("before", "after"):
            outs = []
            for _ in range(5):
                outs.append(await trial(step, 0.05, 0.05, order))
            print(name, order, outs)

asyncio.run(main())
