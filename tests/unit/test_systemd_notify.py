from __future__ import annotations

import socket
from pathlib import Path

import pytest

from app.systemd_notify import SystemdNotifyError, notify, notify_ready


def test_notify_ready_sends_to_filesystem_socket(tmp_path: Path) -> None:
    path = tmp_path / "notify.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    server.bind(str(path))
    server.settimeout(1)
    try:
        notify_ready(environ={"NOTIFY_SOCKET": str(path)})
        assert server.recv(64) == b"READY=1"
    finally:
        server.close()


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="Unix sockets unavailable")
def test_notify_ready_sends_to_abstract_socket() -> None:
    name = f"\0ghc-notify-{__import__('os').getpid()}"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    server.bind(name)
    server.settimeout(1)
    try:
        notify_ready(environ={"NOTIFY_SOCKET": "@" + name[1:]})
        assert server.recv(64) == b"READY=1"
    finally:
        server.close()


@pytest.mark.parametrize("environ", [{}, {"NOTIFY_SOCKET": "relative"}])
def test_notify_rejects_missing_or_relative_address(environ: dict[str, str]) -> None:
    with pytest.raises(SystemdNotifyError):
        notify_ready(environ=environ)


def test_notify_rejects_empty_payload(tmp_path: Path) -> None:
    with pytest.raises(SystemdNotifyError, match="payload"):
        notify("", environ={"NOTIFY_SOCKET": str(tmp_path / "unused.sock")})


def test_notify_wraps_send_failure(tmp_path: Path) -> None:
    with pytest.raises(SystemdNotifyError, match="failed to notify"):
        notify_ready(environ={"NOTIFY_SOCKET": str(tmp_path / "missing.sock")})
