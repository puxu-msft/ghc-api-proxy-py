from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.replay.process import (
    ReplayError,
    ReplayMode,
    ReplayProcess,
    ReplayRequest,
    ReplaySourceSelector,
    ReplayTargetPolicy,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an independent capture replay")
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--entry", required=True)
    parser.add_argument("--attempt", required=True, type=int)
    parser.add_argument("--deadline", required=True, type=float)
    parser.add_argument(
        "--max-deadline",
        type=float,
        default=60.0,
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    process = ReplayProcess(max_deadline_s=args.max_deadline)
    request = ReplayRequest(
        capture_path=args.capture,
        source_entry_id=args.entry,
        selector=ReplaySourceSelector.UPSTREAM_ATTEMPT,
        mode=ReplayMode.WIRE_DIAGNOSTIC,
        target_policy=ReplayTargetPolicy.CURRENT_ROUTE,
        deadline_s=args.deadline,
        attempt_id=args.attempt,
    )
    try:
        result = await process.run(request)
    except ReplayError as error:
        print(
            json.dumps(
                {
                    "error": {
                        "code": error.code,
                        "message": error.message,
                        "not_started": error.not_started,
                    }
                }
            )
        )
        return 2
    print(json.dumps(result.as_dict(), default=str))
    return 0


def main() -> int:
    return asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
