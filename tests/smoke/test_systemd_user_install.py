import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from app.graceful_timeout import (
    DEFAULT_GRACEFUL_TIMEOUT_SECONDS,
    SYSTEMD_STOP_TIMEOUT_SECONDS,
)

PROJECT_ROOT = Path(__file__).parents[2]
INSTALLER = PROJECT_ROOT / "contrib" / "systemd" / "install-user.py"
UNIT_NAMES = {
    "ghc-api-proxy.service",
    "ghc-api-proxy.slice",
    "ghc-api-proxy.socket",
}


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run_installer(
    tmp_path: Path,
    *arguments: str,
    include_systemd_analyze: bool = True,
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    home = tmp_path / "home"
    config_home = tmp_path / "config"
    state_home = tmp_path / "state"
    bin_dir = tmp_path / "bin"
    calls = tmp_path / "calls"
    home.mkdir(exist_ok=True)
    bin_dir.mkdir(exist_ok=True)
    calls.mkdir(exist_ok=True)

    _write_executable(
        bin_dir / "systemctl",
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {calls!s}/systemctl\nexit 99\n",
    )
    if include_systemd_analyze:
        _write_executable(
            bin_dir / "systemd-analyze",
            f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {calls!s}/systemd-analyze\nexit 0\n",
        )

    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(home),
            "PATH": str(bin_dir),
            "XDG_CONFIG_HOME": str(config_home),
            "XDG_STATE_HOME": str(state_home),
            "INSTALLER_SMOKE_SECRET": "must-not-appear",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            str(INSTALLER),
            "--project-dir",
            str(PROJECT_ROOT),
            "--python",
            sys.executable,
            *arguments,
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, config_home / "systemd" / "user", state_home, calls


def test_user_installer_dry_run_check_and_apply_are_inert_and_idempotent(
    tmp_path: Path,
) -> None:
    dry_run, unit_dir, state_home, calls = _run_installer(tmp_path, "--check")

    assert dry_run.returncode == 0, dry_run.stderr
    assert "DRY-RUN" in dry_run.stdout
    assert "systemd-analyze --user verify passed" in dry_run.stdout
    assert "must-not-appear" not in dry_run.stdout + dry_run.stderr
    assert not unit_dir.exists()
    assert not state_home.exists()
    assert not (calls / "systemctl").exists()
    analyze_arguments = (calls / "systemd-analyze").read_text(encoding="utf-8")
    assert analyze_arguments.startswith("--user verify ")
    assert set(Path(argument).name for argument in analyze_arguments.split()[2:]) == UNIT_NAMES

    environment_file = tmp_path / "config with spaces" / "ghc-api-proxy.env"
    applied, unit_dir, state_home, calls = _run_installer(
        tmp_path,
        "--apply",
        "--check",
        "--environment-file",
        str(environment_file),
    )

    assert applied.returncode == 0, applied.stderr
    assert "APPLIED" in applied.stdout
    assert "must-not-appear" not in applied.stdout + applied.stderr
    assert unit_dir.is_dir()
    assert {path.name for path in unit_dir.iterdir()} == UNIT_NAMES
    assert not state_home.exists()
    assert not (calls / "systemctl").exists()

    service = (unit_dir / "ghc-api-proxy.service").read_text(encoding="utf-8")
    socket = (unit_dir / "ghc-api-proxy.socket").read_text(encoding="utf-8")
    resource_slice = (unit_dir / "ghc-api-proxy.slice").read_text(encoding="utf-8")
    assert "User=" not in service
    assert "Group=" not in service
    assert f"WorkingDirectory={PROJECT_ROOT}" in service
    assert (
        f'ExecStart="{Path(sys.executable).resolve()}" -m app start --fd 3 '
        f"--graceful-timeout {DEFAULT_GRACEFUL_TIMEOUT_SECONDS}"
    ) in service
    assert f"TimeoutStopSec={SYSTEMD_STOP_TIMEOUT_SECONDS}s" in service
    assert f"EnvironmentFile=-{str(environment_file).replace(' ', r'\x20')}" in service
    assert "StateDirectory=ghc-api-proxy" in service
    assert "GHC_HISTORY__DB_PATH=%S/ghc-api-proxy/history.db" in service
    assert "GHC_TOKENIZATION__STATE_PATH=%S/ghc-api-proxy/tokenization.json" in service
    assert "WantedBy=default.target" not in service
    assert "WantedBy=sockets.target" in socket
    assert "ListenStream=127.0.0.1:4141" in socket
    assert "MemoryHigh=1G" in resource_slice
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o644 for path in unit_dir.iterdir())

    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in unit_dir.iterdir()
    }
    repeated, _, _, calls = _run_installer(
        tmp_path,
        "--apply",
        "--environment-file",
        str(environment_file),
    )
    after = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in unit_dir.iterdir()
    }

    assert repeated.returncode == 0, repeated.stderr
    assert "UNCHANGED" in repeated.stdout
    assert before == after
    assert not (calls / "systemctl").exists()


def test_user_installer_check_falls_back_when_systemd_analyze_is_unavailable(
    tmp_path: Path,
) -> None:
    result, unit_dir, state_home, calls = _run_installer(
        tmp_path,
        "--check",
        include_systemd_analyze=False,
    )

    assert result.returncode == 0, result.stderr
    assert "text validation passed" in result.stdout
    assert "systemd-analyze unavailable" in result.stdout
    assert not unit_dir.exists()
    assert not state_home.exists()
    assert not any(calls.iterdir())


@pytest.mark.skipif(
    not Path("/usr/bin/systemd-analyze").is_file(),
    reason="systemd-analyze is unavailable",
)
def test_rendered_user_units_pass_real_systemd_analyze_verify(tmp_path: Path) -> None:
    result, unit_dir, state_home, calls = _run_installer(
        tmp_path,
        "--check",
        include_systemd_analyze=False,
    )
    environment = os.environ.copy()
    environment["PATH"] = "/usr/bin:/bin"
    project_dir = tmp_path / "project with spaces"
    project_dir.mkdir()
    environment_file = tmp_path / "config with spaces" / "ghc-api-proxy.env"
    real_verify = subprocess.run(
        [
            sys.executable,
            str(INSTALLER),
            "--project-dir",
            str(project_dir),
            "--python",
            sys.executable,
            "--environment-file",
            str(environment_file),
            "--check",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert real_verify.returncode == 0, real_verify.stderr
    assert "systemd-analyze --user verify passed" in real_verify.stdout
    assert not unit_dir.exists()
    assert not state_home.exists()
    assert not any(calls.iterdir())