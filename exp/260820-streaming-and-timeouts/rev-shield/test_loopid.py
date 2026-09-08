import asyncio

async def test_one():
    print("LOOPID one", id(asyncio.get_running_loop()))

async def test_two():
    print("LOOPID two", id(asyncio.get_running_loop()))
