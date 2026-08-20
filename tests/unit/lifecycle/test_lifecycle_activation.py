from __future__ import annotations

import os
import socket
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app.lifecycle.activation import (
    ActivatedSocketSet,
    ExpectedListener,
    SocketActivationError,
)


def _listener(family: socket.AddressFamily) -> socket.socket:
    listener = socket.socket(family, socket.SOCK_STREAM)
    if family == socket.AF_INET6:
        listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        listener.bind(("::1", 0))
    else:
        listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    return listener


def _expected(name: str, listener: socket.socket) -> ExpectedListener:
    address = listener.getsockname()
    return ExpectedListener(name, listener.family, str(address[0]), int(address[1]))


def test_validated_masters_duplicate_the_same_listener_identity() -> None:
    ipv4 = _listener(socket.AF_INET)
    ipv6 = _listener(socket.AF_INET6)
    activated = ActivatedSocketSet(
        {"http-v6": ipv6, "http-v4": ipv4},
        [_expected("http-v4", ipv4), _expected("http-v6", ipv6)],
    )
    try:
        duplicates = activated.duplicate_for_accept()
        try:
            identities = {identity.name: identity for identity in activated.identities()}
            for name, duplicate in duplicates.items():
                stat = os.fstat(duplicate.fileno())
                assert (stat.st_dev, stat.st_ino) == (
                    identities[name].device,
                    identities[name].inode,
                )
        finally:
            for duplicate in duplicates.values():
                duplicate.close()
    finally:
        activated.close()
        ipv4.close()
        ipv6.close()


def test_rejects_missing_unknown_and_duplicate_expected_names() -> None:
    ipv4 = _listener(socket.AF_INET)
    try:
        expected = [_expected("http-v4", ipv4)]
        with pytest.raises(SocketActivationError, match="names mismatch"):
            ActivatedSocketSet({"wrong": ipv4}, expected)
        with pytest.raises(SocketActivationError, match="must be unique"):
            ActivatedSocketSet(
                {"http-v4": ipv4},
                [expected[0], expected[0]],
            )
    finally:
        ipv4.close()


def test_rejects_wrong_family_address_and_non_listening_socket() -> None:
    ipv4 = _listener(socket.AF_INET)
    ipv6 = _listener(socket.AF_INET6)
    idle = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(SocketActivationError, match="family"):
            ActivatedSocketSet({"http-v4": ipv6}, [_expected("http-v4", ipv4)])
        wrong_address = ExpectedListener(
            "http-v4",
            socket.AF_INET,
            "127.0.0.1",
            ipv4.getsockname()[1] + 1,
        )
        with pytest.raises(SocketActivationError, match="address"):
            ActivatedSocketSet({"http-v4": ipv4}, [wrong_address])
        idle.bind(("127.0.0.1", 0))
        with pytest.raises(SocketActivationError, match="not listening"):
            ActivatedSocketSet({"http-v4": idle}, [_expected("http-v4", idle)])
    finally:
        idle.close()
        ipv4.close()
        ipv6.close()


def test_closed_masters_cannot_be_duplicated() -> None:
    ipv4 = _listener(socket.AF_INET)
    activated = ActivatedSocketSet({"http-v4": ipv4}, [_expected("http-v4", ipv4)])
    activated.close()
    try:
        with pytest.raises(SocketActivationError, match="masters are closed"):
            activated.duplicate_for_accept()
    finally:
        ipv4.close()


def test_systemd_environment_rejects_wrong_pid_and_duplicate_names() -> None:
    expected: list[ExpectedListener] = []
    with pytest.raises(SocketActivationError, match="does not match"):
        ActivatedSocketSet.from_systemd_environment(
            expected,
            environ={"LISTEN_PID": "999", "LISTEN_FDS": "1", "LISTEN_FDNAMES": "http"},
            process_id=1000,
        )
    with pytest.raises(SocketActivationError, match="duplicate names"):
        ActivatedSocketSet.from_systemd_environment(
            expected,
            environ={"LISTEN_PID": "1000", "LISTEN_FDS": "2", "LISTEN_FDNAMES": "x:x"},
            process_id=1000,
        )


def test_systemd_environment_consumes_original_fd_and_unsets_metadata() -> None:
    listener = _listener(socket.AF_INET)
    port = listener.getsockname()[1]
    script = textwrap.dedent(
        """
        import os
        import socket
        from app.lifecycle.activation import ActivatedSocketSet, ExpectedListener

        activated = ActivatedSocketSet.from_systemd_environment(
            [ExpectedListener("http-v4", socket.AF_INET, "127.0.0.1", int(os.environ["PORT"]))]
        )
        activated.close()
        try:
            os.fstat(3)
        except OSError:
            print("FD3_CLOSED=true")
        else:
            print("FD3_CLOSED=false")
        keys = ("LISTEN_PID", "LISTEN_FDS", "LISTEN_FDNAMES")
        print("ENV_CLEARED=" + str(all(key not in os.environ for key in keys)).lower())
        """
    )

    env = os.environ.copy()
    env.update(
        {
            "LISTEN_PID": "__CHILD_PID__",
            "LISTEN_FDS": "1",
            "LISTEN_FDNAMES": "http-v4",
            "PORT": str(port),
            "SOURCE_FD": str(listener.fileno()),
            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        }
    )
    wrapper = (
        "import os; "
        "os.dup2(int(os.environ['SOURCE_FD']), 3); "
        "os.environ['LISTEN_PID']=str(os.getpid()); "
        "exec(" + repr(script) + ")"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", wrapper],
            env=env,
            pass_fds=(listener.fileno(),),
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        listener.close()
    assert result.returncode == 0, result.stderr
    assert "FD3_CLOSED=true" in result.stdout
    assert "ENV_CLEARED=true" in result.stdout
