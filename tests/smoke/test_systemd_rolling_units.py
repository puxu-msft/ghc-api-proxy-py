from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROLLING_DIR = Path(__file__).parents[2] / "contrib" / "systemd" / "rolling"
UNIT_NAMES = (
    "ghc-api-proxy-v4.socket",
    "ghc-api-proxy-v6.socket",
    "ghc-api-proxy-generation@.service",
    "ghc-api-proxy-controller.service",
    "ghc-api-proxy-rolling.target",
    "ghc-api-proxy-rolling.slice",
)


def _text(name: str) -> str:
    return (ROLLING_DIR / name).read_text(encoding="utf-8")


def _launcher_module() -> ModuleType:
    path = ROLLING_DIR / "rolling-generation-launcher.py"
    spec = importlib.util.spec_from_file_location("rolling_generation_launcher", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rolling_socket_units_hold_fixed_dual_stack_4144_for_controller() -> None:
    v4 = _text("ghc-api-proxy-v4.socket")
    v6 = _text("ghc-api-proxy-v6.socket")
    assert "ListenStream=127.0.0.1:4144" in v4
    assert "FileDescriptorName=http-v4" in v4
    assert "ListenStream=[::1]:4144" in v6
    assert "FileDescriptorName=http-v6" in v6
    for content in (v4, v6):
        assert "Accept=no" in content
        assert "Service=ghc-api-proxy-controller.service" in content
        assert ":4141" not in content


def test_generation_template_inherits_both_sockets_and_owns_infinite_drain() -> None:
    service = _text("ghc-api-proxy-generation@.service")
    assert service.count("Sockets=ghc-api-proxy-v4.socket") == 1
    assert service.count("Sockets=ghc-api-proxy-v6.socket") == 1
    for contract in (
        "Type=notify",
        "NotifyAccess=main",
        "Restart=no",
        "KillMode=control-group",
        "TimeoutStopSec=infinity",
        "RuntimeDirectory=ghc-api-proxy/generations/%i",
        "StateDirectory=ghc-api-proxy/generations/%i",
        "EnvironmentFile=/run/ghc-api-proxy/generations/%i.env",
        "Slice=ghc-api-proxy-rolling.slice",
    ):
        assert contract in service


def test_controller_is_finite_and_never_consumes_generation_start_command() -> None:
    controller = _text("ghc-api-proxy-controller.service")
    assert "Type=exec" in controller
    assert "Restart=on-failure" in controller
    assert "TimeoutStopSec=30s" in controller
    assert "\nUser=" not in controller
    assert "Sockets=" not in controller
    assert "start-rolling" not in controller


def test_rolling_target_aggregates_controller_and_both_sockets() -> None:
    target = _text("ghc-api-proxy-rolling.target")
    wants = next(line for line in target.splitlines() if line.startswith("Wants="))
    assert set(wants.removeprefix("Wants=").split()) == {
        "ghc-api-proxy-controller.service",
        "ghc-api-proxy-v4.socket",
        "ghc-api-proxy-v6.socket",
    }


def test_systemd_analyze_accepts_rolling_unit_set(tmp_path: Path) -> None:
    executable = shutil.which("systemd-analyze")
    if executable is None:
        pytest.skip("systemd-analyze unavailable")
    paths: list[Path] = []
    for name in UNIT_NAMES:
        content = _text(name)
        if name.endswith(".service"):
            content = "\n".join(
                "ExecStart=/bin/true" if line.startswith("ExecStart=") else line
                for line in content.splitlines()
            ) + "\n"
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    result = subprocess.run(
        [executable, "verify", *(str(path) for path in paths)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_launcher_binds_generation_to_exact_immutable_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launcher = _launcher_module()
    releases = tmp_path / "releases"
    release = releases / "release-a"
    interpreter = release / ".venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("python", encoding="utf-8")
    interpreter.chmod(0o700)
    config = tmp_path / "config.yaml"
    config.write_text("", encoding="utf-8")
    control = tmp_path / "control.sock"
    monkeypatch.setattr(launcher, "RELEASES_ROOT", releases)
    monkeypatch.setenv("GHC_GENERATION_ID", "g0000000000000001")
    monkeypatch.setenv("GHC_RELEASE_ID", "release-a")
    monkeypatch.setenv("GHC_RELEASE_ROOT", str(release))
    monkeypatch.setenv("GHC_CONTROL_SOCKET", str(control))
    monkeypatch.setenv("GHC_CONFIG", str(config))

    resolved_interpreter, argv = launcher.build_exec("g0000000000000001")

    assert resolved_interpreter == interpreter
    assert argv[:4] == [str(interpreter), "-m", "app", "start-rolling"]
    assert argv[-2:] == ["--config", str(config)]


def test_launcher_rejects_identity_and_release_root_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launcher = _launcher_module()
    monkeypatch.setattr(launcher, "RELEASES_ROOT", tmp_path / "releases")
    monkeypatch.setenv("GHC_GENERATION_ID", "g0000000000000002")
    with pytest.raises(launcher.LaunchError, match="do not match"):
        launcher.build_exec("g0000000000000001")


def test_launcher_rejects_release_traversal_and_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launcher = _launcher_module()
    releases = tmp_path / "releases"
    releases.mkdir()
    monkeypatch.setattr(launcher, "RELEASES_ROOT", releases)
    monkeypatch.setenv("GHC_GENERATION_ID", "g0000000000000001")
    monkeypatch.setenv("GHC_RELEASE_ID", "..")
    monkeypatch.setenv("GHC_RELEASE_ROOT", str(releases / ".."))
    monkeypatch.setenv("GHC_CONTROL_SOCKET", str(tmp_path / "control.sock"))
    config = tmp_path / "config.yaml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GHC_CONFIG", str(config))
    with pytest.raises(launcher.LaunchError, match="release id"):
        launcher.build_exec("g0000000000000001")

    real_release = tmp_path / "real-release"
    (real_release / ".venv" / "bin").mkdir(parents=True)
    link = releases / "release-link"
    link.symlink_to(real_release, target_is_directory=True)
    monkeypatch.setenv("GHC_RELEASE_ID", "release-link")
    monkeypatch.setenv("GHC_RELEASE_ROOT", str(link))
    with pytest.raises(launcher.LaunchError, match=r"symlink|escapes"):
        launcher.build_exec("g0000000000000001")
