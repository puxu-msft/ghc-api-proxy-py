from __future__ import annotations

import os
import socket
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass

LISTEN_FDS_START = 3


class SocketActivationError(RuntimeError):
    """Raised when inherited socket metadata does not match the expected profile."""


@dataclass(frozen=True, slots=True)
class ExpectedListener:
    name: str
    family: socket.AddressFamily
    host: str
    port: int


@dataclass(frozen=True, slots=True)
class ListenerIdentity:
    name: str
    family: socket.AddressFamily
    address: tuple[str, int]
    device: int
    inode: int


class ActivatedSocketSet:
    """Validated master duplicates of systemd-owned listening sockets."""

    def __init__(
        self,
        sockets_by_name: Mapping[str, socket.socket],
        expected: Sequence[ExpectedListener],
    ) -> None:
        expected_by_name = {listener.name: listener for listener in expected}
        if len(expected_by_name) != len(expected):
            raise SocketActivationError("expected listener names must be unique")
        if set(sockets_by_name) != set(expected_by_name):
            missing = sorted(set(expected_by_name) - set(sockets_by_name))
            unknown = sorted(set(sockets_by_name) - set(expected_by_name))
            raise SocketActivationError(
                f"inherited listener names mismatch: missing={missing}, unknown={unknown}"
            )

        masters: dict[str, socket.socket] = {}
        try:
            for name, inherited in sockets_by_name.items():
                listener = expected_by_name[name]
                self._validate_socket(inherited, listener)
                masters[name] = inherited.dup()
        except BaseException:
            for master in masters.values():
                master.close()
            raise
        self._masters = masters
        self._expected = expected_by_name

    @classmethod
    def from_systemd_environment(
        cls,
        expected: Sequence[ExpectedListener],
        *,
        environ: MutableMapping[str, str] | None = None,
        process_id: int | None = None,
    ) -> ActivatedSocketSet:
        values = os.environ if environ is None else environ
        pid = os.getpid() if process_id is None else process_id
        try:
            listen_pid = int(values.get("LISTEN_PID", ""))
            listen_fds = int(values.get("LISTEN_FDS", ""))
        except ValueError as error:
            raise SocketActivationError("LISTEN_PID and LISTEN_FDS must be integers") from error
        if listen_pid != pid:
            raise SocketActivationError(
                f"LISTEN_PID does not match this process: expected {pid}, got {listen_pid}"
            )
        if listen_fds <= 0:
            raise SocketActivationError("LISTEN_FDS must be positive")

        names = values.get("LISTEN_FDNAMES", "").split(":")
        if len(names) != listen_fds or any(not name for name in names):
            raise SocketActivationError(
                "LISTEN_FDNAMES must contain one non-empty name for every inherited fd"
            )
        if len(set(names)) != len(names):
            raise SocketActivationError("LISTEN_FDNAMES contains duplicate names")

        inherited: dict[str, socket.socket] = {}
        try:
            for offset, name in enumerate(names):
                fd = LISTEN_FDS_START + offset
                inherited[name] = socket.socket(fileno=fd)
            return cls(inherited, expected)
        finally:
            for inherited_socket in inherited.values():
                inherited_socket.close()
            for key in ("LISTEN_PID", "LISTEN_FDS", "LISTEN_FDNAMES"):
                values.pop(key, None)

    @staticmethod
    def _validate_socket(sock: socket.socket, expected: ExpectedListener) -> None:
        if expected.family not in {socket.AF_INET, socket.AF_INET6}:
            raise SocketActivationError(
                f"listener {expected.name} uses unsupported family {expected.family}"
            )
        if sock.family != expected.family:
            raise SocketActivationError(
                f"listener {expected.name} has family {sock.family}, expected {expected.family}"
            )
        if sock.type & socket.SOCK_STREAM != socket.SOCK_STREAM:
            raise SocketActivationError(f"listener {expected.name} is not SOCK_STREAM")
        if sock.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) != 1:
            raise SocketActivationError(f"listener {expected.name} is not listening")
        raw_address = sock.getsockname()
        host = str(raw_address[0])
        port = int(raw_address[1])
        if (host, port) != (expected.host, expected.port):
            raise SocketActivationError(
                f"listener {expected.name} address {(host, port)!r} does not match "
                f"{(expected.host, expected.port)!r}"
            )

    def duplicate_for_accept(self) -> dict[str, socket.socket]:
        self._ensure_open()
        return {name: master.dup() for name, master in self._masters.items()}

    def identities(self) -> tuple[ListenerIdentity, ...]:
        self._ensure_open()
        identities: list[ListenerIdentity] = []
        for name in sorted(self._masters):
            master = self._masters[name]
            stat = os.fstat(master.fileno())
            address = master.getsockname()
            identities.append(
                ListenerIdentity(
                    name=name,
                    family=master.family,
                    address=(str(address[0]), int(address[1])),
                    device=stat.st_dev,
                    inode=stat.st_ino,
                )
            )
        return tuple(identities)

    def close(self) -> None:
        masters, self._masters = self._masters, {}
        for master in masters.values():
            master.close()

    def _ensure_open(self) -> None:
        if not self._masters:
            raise SocketActivationError("inherited listener masters are closed")
