#!/usr/bin/env python3
"""Render and optionally install rootless ghc-api-proxy user units."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

UNIT_NAMES = (
    "ghc-api-proxy.service",
    "ghc-api-proxy.socket",
    "ghc-api-proxy.slice",
)
DEFAULT_GRACEFUL_TIMEOUT_SECONDS = 300
SYSTEMD_STOP_TIMEOUT_SECONDS = 330


def _absolute_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("path must be absolute")
    return path.resolve(strict=False)


def _systemd_quote(value: str) -> str:
    if "\n" in value or "\r" in value or "\0" in value:
        raise ValueError("systemd values cannot contain newlines or NUL bytes")
    escaped = value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _systemd_path(value: str) -> str:
    if "\n" in value or "\r" in value or "\0" in value:
        raise ValueError("systemd paths cannot contain newlines or NUL bytes")
    rendered: list[str] = []
    for character in value:
        if character == "%":
            rendered.append("%%")
        elif character.isascii() and (character.isalnum() or character in "/._-+@:"):
            rendered.append(character)
        else:
            rendered.extend(f"\\x{byte:02x}" for byte in character.encode())
    return "".join(rendered)


def _render_units(
    project_dir: Path,
    python: Path,
    environment_file: Path,
) -> dict[str, str]:
    project = _systemd_path(str(project_dir))
    interpreter = _systemd_quote(str(python))
    environment = _systemd_path(str(environment_file))
    state_environment = (
        '"GHC_HISTORY__DB_PATH=%S/ghc-api-proxy/history.db" '
        '"GHC_TOKENIZATION__STATE_PATH=%S/ghc-api-proxy/tokenization.json"'
    )
    service = f"""[Unit]
Description=GitHub Copilot API proxy (user)
Requires=ghc-api-proxy.socket
After=network-online.target ghc-api-proxy.socket
Wants=network-online.target

[Service]
Type=exec
WorkingDirectory={project}
StateDirectory=ghc-api-proxy
StateDirectoryMode=0700
UMask=0077
Environment={state_environment}
EnvironmentFile=-{environment}
ExecStart={interpreter} -m app start --fd 3 --graceful-timeout {DEFAULT_GRACEFUL_TIMEOUT_SECONDS}
Restart=on-failure
RestartSec=2s
KillSignal=SIGTERM
KillMode=control-group
TimeoutStopSec={SYSTEMD_STOP_TIMEOUT_SECONDS}s
Slice=ghc-api-proxy.slice
"""
    socket = """[Unit]
Description=ghc-api-proxy listening socket (user)

[Socket]
ListenStream=127.0.0.1:4141
Accept=no
Backlog=1024
NoDelay=true
FileDescriptorName=http
Service=ghc-api-proxy.service

[Install]
WantedBy=sockets.target
"""
    resource_slice = """[Unit]
Description=Resource controls for ghc-api-proxy (user)

[Slice]
MemoryHigh=1G
MemoryMax=2G
CPUQuota=200%
TasksMax=256
"""
    return {
        "ghc-api-proxy.service": service,
        "ghc-api-proxy.socket": socket,
        "ghc-api-proxy.slice": resource_slice,
    }


def _validate_text(units: Mapping[str, str]) -> None:
    if set(units) != set(UNIT_NAMES):
        raise ValueError("rendered unit set is incomplete")
    service = units["ghc-api-proxy.service"]
    socket = units["ghc-api-proxy.socket"]
    if "\nUser=" in service or "\nGroup=" in service:
        raise ValueError("user service must not select a system account")
    required_service_lines = (
        "StateDirectory=ghc-api-proxy",
        "GHC_HISTORY__DB_PATH=%S/ghc-api-proxy/history.db",
        "GHC_TOKENIZATION__STATE_PATH=%S/ghc-api-proxy/tokenization.json",
        "ExecStart=",
        " --fd 3",
        f" --graceful-timeout {DEFAULT_GRACEFUL_TIMEOUT_SECONDS}",
        f"TimeoutStopSec={SYSTEMD_STOP_TIMEOUT_SECONDS}s",
    )
    if not all(line in service for line in required_service_lines):
        raise ValueError("user service is missing its state or inherited-fd contract")
    if "Accept=no" not in socket or "Service=ghc-api-proxy.service" not in socket:
        raise ValueError("user socket is missing its activation contract")


def _verify_with_systemd_analyze(units: Mapping[str, str]) -> bool:
    executable = shutil.which("systemd-analyze")
    if executable is None:
        print("CHECK: text validation passed; systemd-analyze unavailable")
        return False
    with tempfile.TemporaryDirectory(prefix="ghc-api-proxy-user-units-") as temporary:
        directory = Path(temporary)
        paths: list[Path] = []
        for name in UNIT_NAMES:
            path = directory / name
            path.write_text(units[name], encoding="utf-8")
            paths.append(path)
        result = subprocess.run(
            [executable, "--user", "verify", *(str(path) for path in paths)],
            check=False,
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, file=sys.stderr, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        raise RuntimeError(
            f"systemd-analyze --user verify failed with exit code {result.returncode}"
        )
    print("CHECK: text validation passed; systemd-analyze --user verify passed")
    return True


def _write_atomic(path: Path, content: str) -> bool:
    encoded = content.encode()
    if path.is_file() and path.read_bytes() == encoded:
        return False
    if path.exists() and not path.is_file():
        raise RuntimeError(f"refusing to replace non-file target: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o644)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def _apply(unit_dir: Path, units: Mapping[str, str]) -> None:
    unit_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
    for name in UNIT_NAMES:
        destination = unit_dir / name
        changed = _write_atomic(destination, units[name])
        print(f"{'APPLIED' if changed else 'UNCHANGED'}: {destination}")


def _default_project_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_environment_file() -> Path:
    config_home = Path(
        os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    ).expanduser()
    return (config_home / "ghc-api-proxy" / "ghc-api-proxy.env").resolve(strict=False)


def _unit_dir() -> Path:
    config_home = Path(
        os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    ).expanduser()
    if not config_home.is_absolute():
        raise ValueError("XDG_CONFIG_HOME must be absolute")
    return config_home.resolve(strict=False) / "systemd" / "user"


def _parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render ghc-api-proxy systemd user units. The default is a write-free dry-run; "
            "--apply only copies units and never calls systemctl."
        )
    )
    parser.add_argument("--apply", action="store_true", help="copy units into the user unit dir")
    parser.add_argument("--check", action="store_true", help="validate the rendered units")
    parser.add_argument(
        "--project-dir",
        type=_absolute_path,
        default=_default_project_dir(),
        help="absolute project checkout path",
    )
    parser.add_argument(
        "--python",
        type=_absolute_path,
        default=Path(sys.executable).resolve(),
        help="absolute Python interpreter path",
    )
    parser.add_argument(
        "--environment-file",
        type=_absolute_path,
        default=_default_environment_file(),
        help="optional environment-file path referenced by the unit",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parse_args(arguments)
    project_dir: Path = args.project_dir
    python: Path = args.python
    environment_file: Path = args.environment_file
    if not project_dir.is_dir():
        raise RuntimeError(f"project directory does not exist: {project_dir}")
    if not python.is_file() or not os.access(python, os.X_OK):
        raise RuntimeError(f"Python interpreter is not executable: {python}")

    units = _render_units(project_dir, python, environment_file)
    _validate_text(units)
    if args.check:
        _verify_with_systemd_analyze(units)

    if args.apply:
        _apply(_unit_dir(), units)
    else:
        print("DRY-RUN: no files written; no systemctl command will be run")
        for name in UNIT_NAMES:
            print(f"\n--- {name} ---\n{units[name]}", end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error