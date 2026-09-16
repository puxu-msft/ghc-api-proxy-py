"""Standalone h2 server process, so a client-side memory measurement is not inflated by the server living in the same interpreter.

Prints the chosen port on the first line of stdout and then serves forever.
"""

from __future__ import annotations

import asyncio
import sys

from run_poc import CountingH2Server, start_server


async def main() -> None:
    server = CountingH2Server(expected_requests=10**9, auto_finish_delay=None)
    aio_server, port = await start_server(server)
    print(port, flush=True)
    async with aio_server:
        await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
