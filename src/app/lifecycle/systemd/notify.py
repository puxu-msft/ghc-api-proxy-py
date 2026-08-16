from __future__ import annotations

import os
import socket
from collections.abc import Mapping


class SystemdNotifyError(RuntimeError):
    """Raised when a required systemd notification cannot be delivered."""


def notify(message: str, *, environ: Mapping[str, str] | None = None) -> None:
    values = os.environ if environ is None else environ
    raw_address = values.get("NOTIFY_SOCKET")
    if not raw_address:
        raise SystemdNotifyError("NOTIFY_SOCKET is not set")
    if raw_address.startswith("@"):  # Linux abstract namespace
        address = "\0" + raw_address[1:]
    elif raw_address.startswith("/"):
        address = raw_address
    else:
        raise SystemdNotifyError("NOTIFY_SOCKET must be an absolute or abstract Unix address")

    payload = message.encode("utf-8")
    if not payload:
        raise SystemdNotifyError("notification payload cannot be empty")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.connect(address)
        sent = sock.send(payload)
    except OSError as error:
        raise SystemdNotifyError(f"failed to notify systemd: {error}") from error
    finally:
        sock.close()
    if sent != len(payload):
        raise SystemdNotifyError(
            f"partial systemd notification: sent {sent} of {len(payload)} bytes"
        )


def notify_ready(*, environ: Mapping[str, str] | None = None) -> None:
    notify("READY=1", environ=environ)


def notify_stopping(*, environ: Mapping[str, str] | None = None) -> None:
    notify("STOPPING=1", environ=environ)
