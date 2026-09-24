"""What every function handed to AnyIO's worker processes runs first.

AnyIO starts its workers inside the server's process group, so a Ctrl+C in the terminal reaches every worker as well as the server. A worker turns it into a `KeyboardInterrupt` and AnyIO sends that back as the function's *result*; the server re-raises it inside whichever task was waiting — the token-learning loop, a prompt count — and asyncio treats a `KeyboardInterrupt` escaping a task as fatal to the whole loop. The lifespan is then torn down by cancellation instead of by uvicorn's graceful shutdown: `token_learning.close()` dies with `CancelledError` and the rest of the teardown is skipped. Seen 2026-09-23 on a foreground `ghc-api-proxy start`.

Stopping is the server's decision. A worker only computes, and the server reaps it when its loop closes (AnyIO kills the pool then, and a worker whose parent is gone reads EOF and exits), so a worker ignores the terminal's interrupt. The server's pid travels with every call because the same function also runs in-process — tests substitute an inline `run_sync` — and the server must keep its own SIGINT handling.
"""

import os
import signal
from collections.abc import Callable


def in_worker_process[*Ts, T](server_pid: int, function: Callable[[*Ts], T], *args: *Ts) -> T:
    if os.getpid() != server_pid and signal.getsignal(signal.SIGINT) is not signal.SIG_IGN:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    return function(*args)
