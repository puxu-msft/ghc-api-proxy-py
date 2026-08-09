#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

from app.generation_identity import GenerationIdentityError, parse_generation_id
from app.release_identity import ReleaseIdentityError, parse_release_id

RELEASES_ROOT = Path("/opt/ghc-api-proxy/releases")


class LaunchError(RuntimeError):
    pass


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise LaunchError(f"required environment variable is missing: {name}")
    return value


def build_exec(generation_id: str) -> tuple[Path, list[str]]:
    try:
        parse_generation_id(generation_id)
    except GenerationIdentityError as error:
        raise LaunchError(str(error)) from error
    if _required_environment("GHC_GENERATION_ID") != generation_id:
        raise LaunchError("unit instance and GHC_GENERATION_ID do not match")
    release_id = _required_environment("GHC_RELEASE_ID")
    try:
        parse_release_id(release_id)
    except ReleaseIdentityError as error:
        raise LaunchError(str(error)) from error
    release_root = Path(_required_environment("GHC_RELEASE_ROOT"))
    expected_root = RELEASES_ROOT / release_id
    if not release_root.is_absolute() or release_root != expected_root:
        raise LaunchError(f"release root must be exactly {expected_root}")
    if release_root.is_symlink():
        raise LaunchError("release root must not be a symlink")
    if release_root.resolve().parent != RELEASES_ROOT.resolve():
        raise LaunchError("release root escapes releases directory")
    control_socket = Path(_required_environment("GHC_CONTROL_SOCKET"))
    config = Path(_required_environment("GHC_CONFIG"))
    if not control_socket.is_absolute() or not config.is_absolute():
        raise LaunchError("control socket and config paths must be absolute")
    if not config.is_file():
        raise LaunchError(f"config file does not exist: {config}")
    interpreter = release_root / ".venv" / "bin" / "python"
    current = interpreter
    while current != release_root.parent:
        if current.is_symlink():
            raise LaunchError(f"release path component must not be a symlink: {current}")
        current = current.parent
    if not interpreter.is_file() or not os.access(interpreter, os.X_OK):
        raise LaunchError(f"release interpreter is not executable: {interpreter}")
    argv = [
        str(interpreter),
        "-m",
        "app",
        "start-rolling",
        "--generation-id",
        generation_id,
        "--release-id",
        release_id,
        "--control-socket",
        str(control_socket),
        "--config",
        str(config),
    ]
    return interpreter, argv


def main(arguments: list[str] | None = None) -> int:
    args = sys.argv[1:] if arguments is None else arguments
    if len(args) != 1:
        raise LaunchError("usage: rolling-generation-launcher GENERATION_ID")
    interpreter, argv = build_exec(args[0])
    os.chdir(interpreter.parents[2])
    os.execve(interpreter, argv, os.environ.copy())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, LaunchError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
