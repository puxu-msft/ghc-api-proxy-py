"""Recording real upstream traffic, and replaying it byte-for-byte.

Hand-written rather than vcrpy: the PoC in `docs/tmp/260818-vcrpy-poc.md` found that vcrpy merges
the chunks of a streamed response, and no configuration prevents it. This project's delivery layer
works a block at a time, so a recording that flattens the stream into one chunk cannot reproduce
the timing the layer is built around — which is precisely the class of defect a recording is for.

The reason this exists at all: hand-written stand-ins mirrored what we assumed upstream does. Real
Copilot sends a *different* `item.id` on `output_item.added` and `output_item.done` for the same
item, and no fake ever did, so the assembler paired nothing and streaming returned zero bytes on
the primary path. A recording cannot flatter us that way.

Cassettes are plain JSON so a reviewer can read what upstream actually said. Bodies stay text when
they decode as UTF-8, because the point is to be readable in a diff.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import httpx
import orjson

CASSETTE_VERSION = 1

# Dropped before anything is written. `authorization` is the secret; the rest change on every
# request, and a cassette that records them invites matching on values that can never match again.
VOLATILE_REQUEST_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "x-request-id",
        "x-agent-task-id",
        "x-interaction-id",
    }
)

# The token exchange answers with a live Copilot token and with fields that identify the account
# it belongs to. A cassette is committed, so none of it may travel: `token` is the credential, and
# the rest name the person and the organisations they belong to. Everything else in that response
# describes capabilities, which is what makes the recording worth reading.
REDACTED_RESPONSE_FIELDS = frozenset(
    {
        "token",
        "tracking_id",
        "enterprise_list",
        "organization_list",
    }
)

REDACTION = "REDACTED"


def _encode_chunk(chunk: bytes) -> dict[str, str]:
    """Store a chunk as text when it is text, so a cassette can be read rather than decoded."""
    try:
        return {"text": chunk.decode("utf-8")}
    except UnicodeDecodeError:
        return {"base64": base64.b64encode(chunk).decode("ascii")}


def _decode_chunk(stored: dict[str, str]) -> bytes:
    text = stored.get("text")
    if text is not None:
        return text.encode("utf-8")
    return base64.b64decode(stored.get("base64", ""))


def _scrub_response_body(chunks: list[bytes]) -> list[bytes]:
    """Blank out secrets that arrive in a response body rather than a header."""
    joined = b"".join(chunks)
    try:
        loaded: object = orjson.loads(joined)
    except orjson.JSONDecodeError:
        return chunks
    if not isinstance(loaded, dict):
        return chunks
    body = cast(dict[str, Any], loaded)
    if not REDACTED_RESPONSE_FIELDS & body.keys():
        return chunks
    for name in REDACTED_RESPONSE_FIELDS & body.keys():
        # A list stays a list: replacing it with a string would change the shape the code reads.
        body[name] = [] if isinstance(body[name], list) else REDACTION
    # One chunk: a scrubbed body is no longer the bytes that arrived, so pretending to preserve
    # its framing would be a lie about something nothing depends on.
    return [orjson.dumps(body)]


@dataclass(frozen=True, slots=True)
class Interaction:
    method: str
    path: str
    # Whether the recorded request carried an Authorization header. The value is a secret and is
    # never stored, but the *fact* is what makes a replay able to notice that the code under test
    # stopped authenticating — which is how the catalog fetch went out bare and nothing said so.
    authenticated: bool
    status: int
    headers: dict[str, str]
    chunks: list[bytes]

    def as_json(self) -> dict[str, Any]:
        return {
            "request": {
                "method": self.method,
                "path": self.path,
                "authenticated": self.authenticated,
            },
            "response": {
                "status": self.status,
                "headers": self.headers,
                "chunks": [_encode_chunk(chunk) for chunk in self.chunks],
            },
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> Interaction:
        request = cast(dict[str, Any], raw["request"])
        response = cast(dict[str, Any], raw["response"])
        stored = cast(list[dict[str, str]], response["chunks"])
        return cls(
            method=str(request["method"]),
            path=str(request["path"]),
            authenticated=bool(request.get("authenticated", False)),
            status=int(response["status"]),
            headers=dict(cast(dict[str, str], response.get("headers", {}))),
            chunks=[_decode_chunk(chunk) for chunk in stored],
        )


@dataclass
class Cassette:
    """An ordered recording of what upstream said."""

    interactions: list[Interaction] = field(default_factory=lambda: list[Interaction]())

    def write(self, path: Path) -> None:
        payload = {
            "version": CASSETTE_VERSION,
            "interactions": [interaction.as_json() for interaction in self.interactions],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2) + b"\n")

    @classmethod
    def read(cls, path: Path) -> Cassette:
        raw = cast(dict[str, Any], orjson.loads(path.read_bytes()))
        version = int(raw.get("version", 0))
        if version != CASSETTE_VERSION:
            raise ValueError(f"cassette {path} is version {version}, expected {CASSETTE_VERSION}")
        entries = cast(list[dict[str, Any]], raw["interactions"])
        return cls(interactions=[Interaction.from_json(entry) for entry in entries])


class _ReplayStream(httpx.AsyncByteStream):
    """Yields the recorded chunks, one at a time, exactly as they arrived."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk

    def __iter__(self) -> Iterator[bytes]:
        return iter(self._chunks)


class CassetteExhausted(RuntimeError):
    """The code under test made a request the recording does not have."""


class UnauthenticatedRequest(RuntimeError):
    """A request that was authenticated when recorded went out bare on replay."""


class ReplayTransport(httpx.MockTransport):
    """Answers from a cassette, in the order it was recorded.

    Matched on method and path in sequence rather than on the request body. Bodies carry a
    per-request id and the recorded one can never be sent again; sequence is the only thing that
    both sides agree on. A request the cassette does not have is an error rather than a default
    response, because a silent default is how a stand-in stops resembling the thing it stands for.
    """

    def __init__(self, cassette: Cassette) -> None:
        self._remaining = list(cassette.interactions)
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        for index, interaction in enumerate(self._remaining):
            if interaction.method == request.method and interaction.path == path:
                del self._remaining[index]
                if interaction.authenticated and "authorization" not in request.headers:
                    raise UnauthenticatedRequest(
                        f"{request.method} {path} carried no Authorization, but the recording "
                        "was made with one — upstream would refuse this"
                    )
                return httpx.Response(
                    interaction.status,
                    headers=interaction.headers,
                    stream=_ReplayStream(interaction.chunks),
                )
        raise CassetteExhausted(f"cassette has no recorded {request.method} {path}")


class RecordingTransport(httpx.AsyncBaseTransport):
    """Passes traffic through to the real upstream and keeps what came back."""

    def __init__(self, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self._inner = inner or httpx.AsyncHTTPTransport()
        self.cassette = Cassette()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        chunks = [chunk async for chunk in response.aiter_raw()]
        await response.aclose()

        # Scrubbed for the cassette only. The live code downstream must receive what upstream
        # actually sent: handing it the redacted body once made the token manager authenticate
        # with the literal word REDACTED, and upstream said so.
        recorded = _scrub_response_body(chunks)
        self.cassette.interactions.append(
            Interaction(
                method=request.method,
                path=request.url.path,
                authenticated="authorization" in request.headers,
                status=response.status_code,
                headers={
                    name: value
                    for name, value in response.headers.items()
                    if name.lower() not in VOLATILE_REQUEST_HEADERS
                },
                chunks=recorded,
            )
        )
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            stream=_ReplayStream(chunks),
            request=request,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()
