from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay CLI is disabled until a controlled History source authority is available"
    )
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
    del args
    print(
        json.dumps(
            {
                "error": {
                    "code": "replay_cli_unavailable",
                    "message": (
                        "replay CLI is disabled because no controlled History "
                        "source authority is available"
                    ),
                    "not_started": True,
                }
            }
        )
    )
    return 2


def main() -> int:
    return asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
