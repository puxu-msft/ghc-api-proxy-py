"""Recording real upstream traffic, and replaying it byte-for-byte.

Hand-written rather than vcrpy: the PoC in `.dev/docs/test-infrastructure/reports/260818-vcrpy-poc.md` found that vcrpy merges
the chunks of a streamed response, and no configuration prevents it. This project's delivery layer works a block at a time, so a recording that flattens the stream into one chunk cannot reproduce the timing the layer is built around — which is precisely the class of defect a recording is for.

The reason this exists at all: hand-written stand-ins mirrored what we assumed upstream does. Real
Copilot sends a *different* `item.id` on `output_item.added` and `output_item.done` for the same item, and no fake ever did, so the assembler paired nothing and streaming returned zero bytes on the primary path. A recording cannot flatter us that way.

Cassettes are plain JSON so a reviewer can read what upstream actually said. Bodies stay text when they decode as UTF-8, because the point is to be readable in a diff.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import httpx2
import orjson

CASSETTE_VERSION = 1

# Dropped before anything is written. `authorization` is the secret; the rest change on every request, and a cassette that records them invites matching on values that can never match again.
VOLATILE_REQUEST_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "x-request-id",
        "x-agent-task-id",
        "x-interaction-id",
    }
)

# Response headers kept in a cassette, by name. An allowlist rather than a denylist: three rounds of reading a capture by hand each found an identifying header the round before had missed (`x-oauth-client-id`, then `x-request-id`, then `copilot-edits-session`), which is what a denylist does. Nothing downstream reads a response header, so keeping few costs nothing, and a header that turns out to matter can be added deliberately.
KEPT_RESPONSE_HEADERS = frozenset(
    {
        "content-type",
        "transfer-encoding",
        "cache-control",
    }
)

# The token exchange answers with a live Copilot token and with fields that identify the account it belongs to. A cassette is committed, so none of it may travel: `token` is the credential, and the rest name the person and the organisations they belong to. Everything else in that response describes capabilities, which is what makes the recording worth reading.
REDACTED_RESPONSE_FIELDS = frozenset(
    {
        "token",
        "tracking_id",
        "enterprise_list",
        "organization_list",
        # A stable hash of the account, sent back inside every Responses frame.
        "safety_identifier",
    }
)

REDACTION = "REDACTED"

# The token exchange answers with a real expiry, and a cassette holding one stops working roughly half an hour after it was recorded: the manager judges the cached token stale, exchanges again, and the replay — which serves each recorded interaction once — reports the cassette exhausted.
# Rewritten to a fixed far-future instant, which is a scrub rather than a lie: when the token expires is not what any of these recordings are about, and leaving it real makes them expire too.
FAR_FUTURE_EPOCH = 4102444800  # 2100-01-01T00:00:00Z
PINNED_RESPONSE_FIELDS: dict[str, object] = {"expires_at": FAR_FUTURE_EPOCH}


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


def _scrub_value(value: object) -> object:
    """Redact the named fields wherever they appear, however deeply nested.

    By field name at any depth rather than at the top level: `safety_identifier` rides inside the `response` object of an SSE frame, and a scrubber that only looked at the outermost object walked straight past it while reporting success.
    """
    if isinstance(value, dict):
        entry = cast(dict[str, Any], value)
        scrubbed: dict[str, Any] = {}
        for name, inner in entry.items():
            if name in PINNED_RESPONSE_FIELDS:
                scrubbed[name] = PINNED_RESPONSE_FIELDS[name]
            elif name in REDACTED_RESPONSE_FIELDS:
                # Shapes are preserved: a list that became a string would change what code reads.
                scrubbed[name] = [] if isinstance(inner, list) else REDACTION
            else:
                scrubbed[name] = _scrub_value(inner)
        return scrubbed
    if isinstance(value, list):
        return [_scrub_value(item) for item in cast(list[Any], value)]
    return value


def _scrub_json(raw: bytes) -> bytes | None:
    """Scrub one JSON document, or None when it is not one or nothing changed."""
    try:
        loaded: object = orjson.loads(raw)
    except orjson.JSONDecodeError:
        return None
    scrubbed = _scrub_value(loaded)
    rendered = orjson.dumps(scrubbed)
    return rendered if rendered != orjson.dumps(loaded) else None


def _scrub_sse(chunks: list[bytes]) -> list[bytes]:
    """Scrub every `data:` payload in a stream, then hand back the same chunk boundaries.

    Joined first because a frame does not respect chunk boundaries: in a real capture only 9 of 26 chunks ended on a frame, so scrubbing chunk by chunk parsed truncated JSON, failed silently and left the identifiers in place. Re-split by the original lengths afterwards, because those boundaries are the one thing this recorder exists to preserve.

    Redaction can change a payload's length, so the split follows each chunk's *share* of the stream rather than its byte offset. Boundaries stay where a reader would expect them: at the same point in the same frame.
    """
    lengths = [len(chunk) for chunk in chunks]
    joined = b"".join(chunks)

    scrubbed_lines: list[bytes] = []
    for line in joined.split(b"\n"):
        if line.startswith(b"data: "):
            replacement = _scrub_json(line[len(b"data: ") :])
            scrubbed_lines.append(b"data: " + replacement if replacement is not None else line)
        else:
            scrubbed_lines.append(line)
    scrubbed = b"\n".join(scrubbed_lines)

    if scrubbed == joined:
        return chunks
    return _resplit(scrubbed, lengths)


def _resplit(body: bytes, lengths: list[int]) -> list[bytes]:
    """Cut `body` into as many pieces as `lengths`, keeping their relative sizes."""
    total = sum(lengths)
    if total == 0:
        return [body]
    pieces: list[bytes] = []
    start = 0
    for index, length in enumerate(lengths):
        if index == len(lengths) - 1:
            pieces.append(body[start:])
            break
        end = start + round(len(body) * length / total)
        pieces.append(body[start:end])
        start = end
    return pieces


def _scrub_response_body(chunks: list[bytes], content_type: str) -> list[bytes]:
    """Remove identifying fields from a response body, whatever shape it arrives in."""
    if "text/event-stream" in content_type:
        return _without_empties(_scrub_sse(chunks))
    replacement = _scrub_json(b"".join(chunks))
    if replacement is None:
        return _without_empties(chunks)
    # One chunk: a rewritten body is no longer the bytes that arrived, so pretending to preserve its framing would be a lie about something nothing depends on.
    return [replacement]


def _without_empties(chunks: list[bytes]) -> list[bytes]:
    """Drop zero-length chunks, in the one place both ways of producing one pass through.

    A replay hands back only chunks with content, so a cassette holding an empty one claims a boundary the replay can never reproduce. They arrive two ways: upstream ending the stream with an empty read, and `_resplit` rounding a share down to nothing while redacting.
    """
    return [chunk for chunk in chunks if chunk]


# Kept in clear so a mismatch says something useful; the digest below is what actually decides.
SHAPE_FIELDS = ("model", "stream")

# Extensions worth replaying. Only `http_version`: it is what product code reads, and it is text.
# `reason_phrase` is bytes in httpx and carries nothing a test could assert on, so recording it bought a round-trip conversion and no information.
RECORDED_EXTENSIONS = frozenset({"http_version"})


def _request_shape(request: httpx2.Request) -> dict[str, Any]:
    """What decides whether a recorded answer still applies to this request.

    A digest of the whole body rather than a chosen few fields. Naming fields meant the ones left unnamed went unchecked: emptying `input` entirely — losing every message — still matched a recording that agreed on `model` and `stream`. The outbound body was measured to be identical across runs, so the whole of it can be the criterion and nothing has to be judged unimportant.

    `model` and `stream` are also kept in clear, so a mismatch reports something a reader can act on rather than two hashes.
    """
    try:
        loaded: object = orjson.loads(request.content) if request.content else None
    except orjson.JSONDecodeError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    body = cast(dict[str, Any], loaded)
    named = {name: body[name] for name in SHAPE_FIELDS if name in body}
    return {**named, "digest": sha256(orjson.dumps(body, option=orjson.OPT_SORT_KEYS)).hexdigest()}


def _keep_response_header(name: str) -> bool:
    return name.lower() in KEPT_RESPONSE_HEADERS


@dataclass(slots=True)
class Interaction:
    method: str
    path: str
    # Whether the recorded request carried an Authorization header. The value is a secret and is never stored, but the *fact* is what makes a replay able to notice that the code under test stopped authenticating — which is how the catalog fetch went out bare and nothing said so.
    authenticated: bool
    # `http_version` and the like. Product code propagates `response.extensions` — see `pipeline/executor.py` and `anthropic/client.py` — so a replay that dropped them would make
    # HTTP/2 traffic look like HTTP/1.1 to everything downstream.
    extensions: dict[str, str]
    # Where these bytes came from, because it changes what they prove. A live recording carries the wire's own chunk boundaries; one rebuilt from the history database carries frame boundaries instead, and only a recording can settle how chunks actually fell.
    source: str
    # The few request fields whose change would make the recorded answer the wrong one. Matching on method and path alone let a request for a different model, or a non-streaming one, be served this recording without a word; matching on the whole body cannot work, because it carries a per-request id that can never be sent again.
    request_shape: dict[str, Any]
    status: int
    headers: dict[str, str]
    chunks: list[bytes]

    def as_json(self) -> dict[str, Any]:
        return {
            "request": {
                "method": self.method,
                "path": self.path,
                "authenticated": self.authenticated,
                "shape": self.request_shape,
            },
            "response": {
                "status": self.status,
                "headers": self.headers,
                "extensions": self.extensions,
                "source": self.source,
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
            request_shape=dict(cast(dict[str, Any], request.get("shape", {}))),
            status=int(response["status"]),
            headers=dict(cast(dict[str, str], response.get("headers", {}))),
            extensions=dict(cast(dict[str, str], response.get("extensions", {}))),
            source=str(response.get("source", "unknown")),
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


class _ReplayStream(httpx2.AsyncByteStream):
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


class RequestShapeChanged(RuntimeError):
    """The request asks for something other than what the recording answers."""


class ReplayTransport(httpx2.MockTransport):
    """Answers from a cassette, in the order it was recorded.

    Matched on method and path in sequence rather than on the request body. Bodies carry a per-request id and the recorded one can never be sent again; sequence is the only thing that both sides agree on. A request the cassette does not have is an error rather than a default response, because a silent default is how a stand-in stops resembling the thing it stands for.
    """

    def __init__(self, cassette: Cassette) -> None:
        self._remaining = list(cassette.interactions)
        super().__init__(self._handle)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        for index, interaction in enumerate(self._remaining):
            if interaction.method == request.method and interaction.path == path:
                del self._remaining[index]
                shape = _request_shape(request)
                if shape != interaction.request_shape:
                    raise RequestShapeChanged(
                        f"{request.method} {path} was recorded for {interaction.request_shape} "
                        f"but this request asks for {shape}"
                    )
                if interaction.authenticated and "authorization" not in request.headers:
                    raise UnauthenticatedRequest(
                        f"{request.method} {path} carried no Authorization, but the recording "
                        "was made with one — upstream would refuse this"
                    )
                return httpx2.Response(
                    interaction.status,
                    headers=interaction.headers,
                    stream=_ReplayStream(interaction.chunks),
                    # httpx reads these as bytes and a cassette holds text, so they go back as bytes on the way out.
                    extensions=cast(
                        dict[str, Any],
                        {name: value.encode() for name, value in interaction.extensions.items()},
                    ),
                )
        raise CassetteExhausted(f"cassette has no recorded {request.method} {path}")


class RecordingTransport(httpx2.AsyncBaseTransport):
    """Passes traffic through to the real upstream and keeps what came back."""

    def __init__(self, inner: httpx2.AsyncBaseTransport | None = None) -> None:
        self._inner = inner or httpx2.AsyncHTTPTransport()
        self.cassette = Cassette()

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        response = await self._inner.handle_async_request(request)
        chunks = [chunk async for chunk in response.aiter_raw()]
        await response.aclose()

        # Scrubbed for the cassette only. The live code downstream must receive what upstream actually sent: handing it the redacted body once made the token manager authenticate with the literal word REDACTED, and upstream said so.
        recorded = _scrub_response_body(chunks, response.headers.get("content-type", ""))
        self.cassette.interactions.append(
            Interaction(
                method=request.method,
                path=request.url.path,
                authenticated="authorization" in request.headers,
                # Only the textual, reproducible ones. A network stream or a socket object means nothing on replay, and writing it to a cassette would be writing a live handle.
                extensions={
                    name: value.decode() if isinstance(value, bytes) else str(value)
                    for name, value in response.extensions.items()
                    if name in RECORDED_EXTENSIONS
                },
                request_shape=_request_shape(request),
                source="live-recording",
                status=response.status_code,
                headers={
                    name: value
                    for name, value in response.headers.items()
                    if _keep_response_header(name)
                },
                chunks=recorded,
            )
        )
        return httpx2.Response(
            response.status_code,
            headers=response.headers,
            stream=_ReplayStream(chunks),
            request=request,
            # Passed through: the code below this transport is the real code, and dropping these made an HTTP/2 exchange look like HTTP/1.1 to it while recording.
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()
