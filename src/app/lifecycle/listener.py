"""Binding the listener a directly-run process owns.

Under systemd the listener comes from socket activation and the process never binds.
Run directly there is nobody to inherit from, so the process binds its own.
It binds the way the spec's smooth restart needs, with `SO_REUSEPORT`.

That option is what lets the replacement bind the same port while the old process still listens.
Without it the second bind fails with EADDRINUSE.
The restart then has to become a stop-then-start, with a window where the port answers nothing.

The result is wrapped in `ActivatedSocketSet`.
A self-bound listener and an inherited one are then the same kind of thing from here on.
Both reach `UvicornListenerAdapter` unchanged.
"""

import socket

from app.socket_activation import ActivatedSocketSet, ExpectedListener

LISTENER_NAME = "http"


class ListenerBindError(RuntimeError):
    """The configured address could not be turned into a listening socket."""


def _resolve(host: str, port: int) -> tuple[socket.AddressFamily, tuple[str, int]]:
    """Pick one address to bind, preferring IPv4 so `getsockname` matches what was configured."""
    try:
        candidates = socket.getaddrinfo(
            host or None,
            port,
            type=socket.SOCK_STREAM,
            flags=socket.AI_PASSIVE,
        )
    except OSError as error:
        raise ListenerBindError(f"cannot resolve {host!r}:{port}: {error}") from error
    for family, _type, _proto, _canon, address in candidates:
        if family is socket.AF_INET:
            return family, (str(address[0]), int(address[1]))
    for family, _type, _proto, _canon, address in candidates:
        if family is socket.AF_INET6:
            return family, (str(address[0]), int(address[1]))
    raise ListenerBindError(f"no IPv4 or IPv6 address for {host!r}:{port}")


def adopt_listener(fd: int) -> ActivatedSocketSet:
    """Wrap a listening socket this process was handed, without binding anything.

    The address is read back off the socket rather than taken from configuration, so an inherited
    listener cannot be described as something it is not.
    """
    try:
        sock = socket.socket(fileno=fd)
    except OSError as error:
        raise ListenerBindError(f"cannot adopt fd {fd}: {error}") from error
    try:
        bound = sock.getsockname()
        expected = ExpectedListener(
            name=LISTENER_NAME,
            family=sock.family,
            host=str(bound[0]),
            port=int(bound[1]),
        )
        return ActivatedSocketSet({LISTENER_NAME: sock}, [expected])
    except OSError as error:
        raise ListenerBindError(f"cannot adopt fd {fd}: {error}") from error
    finally:
        sock.close()


def bind_listener(host: str, port: int, *, reuse_port: bool = True) -> ActivatedSocketSet:
    """Bind and listen, returning the same listener container the systemd path produces.

    `reuse_port` defaults on.
    A process that binds without it cannot be smoothly replaced, and by then it is too late to say.
    """
    family, address = _resolve(host, port)
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        # Lets a restart rebind while the old socket is in TIME_WAIT.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if reuse_port:
            if not hasattr(socket, "SO_REUSEPORT"):
                raise ListenerBindError("SO_REUSEPORT is unavailable on this platform")
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(address)
        sock.listen()
        sock.set_inheritable(True)
        # Read the address back: port 0 means the kernel chose, and the caller must be told which.
        bound = sock.getsockname()
        expected = ExpectedListener(
            name=LISTENER_NAME,
            family=family,
            host=str(bound[0]),
            port=int(bound[1]),
        )
        return ActivatedSocketSet({LISTENER_NAME: sock}, [expected])
    except OSError as error:
        raise ListenerBindError(f"cannot bind {address!r}: {error}") from error
    finally:
        # ActivatedSocketSet keeps its own duplicate, so this one is ours to close either way.
        sock.close()
