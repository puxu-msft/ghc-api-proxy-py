"""Raw HTTP client for the Command Code upstream."""

import asyncio
import hashlib
import logging
import secrets
import time
from collections.abc import Mapping
from typing import Any, cast
from uuid import uuid4

import httpx2
import orjson

from app.config.schema import CommandCodeProviderConfig
from app.model_provider.http_errors import upstream_error_from_response
from app.model_provider.upstream_errors import (
    normalize_upstream_cleanup_error,
    normalize_upstream_error,
    normalize_upstream_response_error,
    read_response_body_with_evidence,
)
from app.observability.raw_capture import (
    activate_pending_upstream_capture,
    observe_active_upstream_request,
)
from app.pipeline.exceptions import UpstreamError, UpstreamRateLimit, UpstreamRejected
from app.pipeline.translation_driver.commandcode import CommandCodeEventAccumulator
from app.wire_json import dumps

logger = logging.getLogger(__name__)

GENERATE_PATH = "/alpha/generate"
MODELS_PATH = "/provider/v1/models"
FINGERPRINT_PATH = "/alpha/fingerprint/record"
LIFECYCLE_PATH = "/alpha/lifecycle-events"
INITIALIZATION_RETRY_DELAY = 0.0

_OWNED_HEADERS = frozenset(
    {
        "accept",
        "authorization",
        "cache-control",
        "content-type",
        "host",
        "traceparent",
        "x-cli-environment",
        "x-cmd-zdr",
        "x-co-flag",
        "x-command-code-version",
        "x-project-slug",
        "x-session-id",
        "x-taste-learning",
    }
)


def _buffered_response_extensions(
    response: httpx2.Response,
    raw_body: bytes,
) -> dict[str, Any]:
    """Keep transport facts while dropping the stream consumed below."""
    extensions = {
        key: value
        for key, value in response.extensions.items()
        if key != "network_stream"
    }
    extensions["upstream_raw_response_body"] = raw_body
    extensions["upstream_transport_status_code"] = response.status_code
    extensions["upstream_transport_headers"] = dict(response.headers)
    return extensions


def _traceparent() -> str:
    return f"00-{secrets.token_hex(16)}-{secrets.token_hex(8)}-01"


def _fingerprint() -> dict[str, Any]:
    """Generate a stable opaque fingerprint without reading host identifiers."""
    seed = secrets.token_bytes(32)
    digest = hashlib.sha256(seed).hexdigest()
    return {
        "thumbmark": digest,
        "components": {
            "machineIdHash": hashlib.sha256(seed + b"machine").hexdigest(),
            "macHashes": [hashlib.sha256(seed + b"network").hexdigest()],
            "osUserHash": hashlib.sha256(seed + b"user").hexdigest(),
            "hostnameHash": hashlib.sha256(seed + b"host").hexdigest(),
            "gitEmailHash": hashlib.sha256(seed + b"git").hexdigest(),
            "platform": "linux",
            "arch": "x64",
            "osRelease": "proxy",
            "cpuModel": "proxy",
            "cpuCount": 1,
            "memGiB": 1,
            "isContainer": True,
            "timezone": "UTC",
            "runtime": "proxy",
            "collectorVersion": 1,
        },
    }


def _event_error(
    event: Mapping[str, Any],
    raw: bytes,
    *,
    transport_status_code: int,
    transport_headers: Mapping[str, str],
) -> BaseException:
    nested = event.get("error")
    message = ""
    if isinstance(nested, Mapping):
        message = str(cast(Mapping[str, Any], nested).get("message") or "")
    if not message:
        message = str(event.get("message") or "Command Code upstream error")
    status = 502
    if message.startswith("<") and ">" in message[:5]:
        try:
            status = int(message[1 : message.index(">")])
        except ValueError:
            status = 502
    headers = {"content-type": "application/x-ndjson"}
    if status in {402, 429}:
        error: BaseException = UpstreamRateLimit(
            message,
            retry_after=30,
            headers=headers,
            body=message,
            body_bytes=raw,
            content_type=headers["content-type"],
            body_observed=True,
        )
    elif 400 <= status < 500:
        error = UpstreamRejected(
            message,
            status_code=400 if status == 422 else status,
            headers=headers,
            body=message,
            body_bytes=raw,
            content_type=headers["content-type"],
            body_observed=True,
        )
    else:
        error = UpstreamError(
            message,
            status_code=status,
            headers=headers,
            body=message,
            body_bytes=raw,
            content_type=headers["content-type"],
            body_observed=True,
        )
    return _attach_transport_evidence(
        error,
        transport_status_code=transport_status_code,
        transport_headers=transport_headers,
    )


def _attach_transport_evidence(
    error: BaseException,
    *,
    transport_status_code: int,
    transport_headers: Mapping[str, str],
) -> BaseException:
    transport_error = cast(Any, error)
    transport_error.transport_status_code = transport_status_code
    transport_error.transport_headers = dict(transport_headers)
    return error


class CommandCodeClient:
    def __init__(
        self,
        http_client: httpx2.AsyncClient,
        config: CommandCodeProviderConfig,
    ) -> None:
        self._http = http_client
        self._config = config
        self._base_url = config.api_base_url.rstrip("/")
        self._fingerprint = _fingerprint()
        self._default_session_id = str(uuid4())
        self._initialization_lock = asyncio.Lock()
        self._next_initialization_at = 0.0

    @property
    def base_url(self) -> str:
        return self._base_url

    def _headers(
        self,
        *,
        stream: bool,
        session_id: str,
        extra_headers: Mapping[str, str] | None = None,
        lifecycle: bool = False,
        include_zdr: bool = True,
    ) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "text/event-stream" if stream else "application/json",
            "Authorization": "Bearer " + self._config.api_key,
            "Cache-Control": "no-cache",
            "Content-Type": "application/json",
            "traceparent": _traceparent(),
            "x-cli-environment": "production",
            "x-command-code-version": self._config.command_code_version,
            "x-co-flag": "false",
            "x-project-slug": self._config.project_slug,
            "x-session-id": session_id,
            "x-taste-learning": "false",
        }
        if include_zdr and self._config.zdr:
            headers["x-cmd-zdr"] = "1"
        if extra_headers:
            for name, value in extra_headers.items():
                if name.lower() not in _OWNED_HEADERS:
                    headers[str(name)] = str(value)
                elif (
                    include_zdr
                    and name.lower() == "x-cmd-zdr"
                    and str(value) == "1"
                ):
                    headers["x-cmd-zdr"] = "1"
        if lifecycle:
            headers.pop("x-session-id", None)
            headers.pop("x-project-slug", None)
        return headers

    async def _send_response(
        self,
        request: httpx2.Request,
        *,
        stream: bool,
    ) -> httpx2.Response:
        try:
            with activate_pending_upstream_capture():
                observe_active_upstream_request(request)
                response = await self._http.send(request, stream=True)
        except BaseException as error:
            normalized = normalize_upstream_error(error)
            if normalized is None:
                raise
            raise normalized from error
        if not response.is_success:
            primary: BaseException | None = None
            try:
                try:
                    await read_response_body_with_evidence(response)
                except BaseException as error:
                    normalized = normalize_upstream_response_error(error, response)
                    if normalized is not None:
                        raise normalized from error
                    raise
                raise upstream_error_from_response(response)
            except BaseException as error:
                primary = error
                raise
            finally:
                try:
                    await response.aclose()
                except BaseException as cleanup:
                    if primary is None:
                        raise normalize_upstream_cleanup_error(cleanup, response) from cleanup
                    primary.add_note(
                        f"upstream response cleanup failed: {type(cleanup).__qualname__}"
                    )
        if stream:
            return response
        return await self._aggregate_response(response)

    async def _aggregate_response(self, response: httpx2.Response) -> httpx2.Response:
        raw = bytearray()
        raw_body: bytes | None = None

        def canonical_raw_body() -> bytes:
            nonlocal raw_body
            if raw_body is None:
                raw_body = bytes(raw)
                response.extensions["upstream_raw_response_body"] = raw_body
            return raw_body

        events: list[dict[str, Any]] = []
        pending: list[bytes] = []
        primary: BaseException | None = None
        try:
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                start = 0
                while True:
                    newline = chunk.find(b"\n", start)
                    if newline < 0:
                        if start < len(chunk):
                            pending.append(chunk[start:])
                        break
                    if newline > start:
                        pending.append(chunk[start:newline])
                    line = b"".join(pending) if pending else b""
                    pending.clear()
                    self._append_event(line, events)
                    start = newline + 1
            if pending:
                self._append_event(b"".join(pending), events)
            for event in events:
                if event.get("type") == "error":
                    raise _event_error(
                        event,
                        canonical_raw_body(),
                        transport_status_code=response.status_code,
                        transport_headers=response.headers,
                    )
            accumulator = CommandCodeEventAccumulator()
            for event in events:
                accumulator.push(event)
            if not accumulator.blocks:
                raise UpstreamRateLimit(
                    "Command Code returned no output",
                    retry_after=10,
                    headers=dict(response.headers),
                    body_bytes=canonical_raw_body(),
                    body_observed=True,
                    content_type=response.headers.get("content-type", ""),
                )
            finish_events = [
                event for event in events if event.get("type") == "finish"
            ]
            if not finish_events:
                raise UpstreamRateLimit(
                    "Command Code stream ended without a terminal event",
                    retry_after=10,
                    headers=dict(response.headers),
                    body_bytes=canonical_raw_body(),
                    body_observed=True,
                    content_type=response.headers.get("content-type", ""),
                )
            usage: Mapping[str, Any] | None = None
            for event in events:
                if event.get("type") == "finish-step":
                    candidate = event.get("usage")
                    if isinstance(candidate, Mapping):
                        usage = cast(Mapping[str, Any], candidate)
                if event.get("type") == "finish":
                    candidate = event.get("totalUsage") or event.get("usage")
                    if isinstance(candidate, Mapping):
                        usage = cast(Mapping[str, Any], candidate)
            output_tokens = (
                usage.get("outputTokens", usage.get("output_tokens"))
                if usage is not None
                else None
            )
            if not isinstance(output_tokens, int) or isinstance(output_tokens, bool):
                raise UpstreamRateLimit(
                    "Command Code returned no usage",
                    retry_after=10,
                    headers=dict(response.headers),
                    body_bytes=canonical_raw_body(),
                    body_observed=True,
                    content_type=response.headers.get("content-type", ""),
                )
            if output_tokens == 0:
                raise UpstreamRateLimit(
                    "Command Code returned zero output tokens",
                    retry_after=10,
                    headers=dict(response.headers),
                    body_bytes=canonical_raw_body(),
                    body_observed=True,
                    content_type=response.headers.get("content-type", ""),
                )
            model = ""
            try:
                request_payload = cast(object, orjson.loads(response.request.content))
                if isinstance(request_payload, dict):
                    request_map = cast(dict[str, Any], request_payload)
                    params = request_map.get("params")
                    if isinstance(params, dict):
                        params_map = cast(dict[str, Any], params)
                        candidate_model = params_map.get("model")
                        if isinstance(candidate_model, str):
                            model = candidate_model
            except orjson.JSONDecodeError:
                pass
            body = dumps({"model": model, "events": events})
            raw_body = canonical_raw_body()
            return httpx2.Response(
                200,
                content=body,
                headers={"content-type": "application/json"},
                request=response.request,
                extensions=_buffered_response_extensions(response, raw_body),
            )
        except BaseException as error:
            primary = error
            canonical_raw_body()
            if isinstance(error, (UpstreamError, UpstreamRejected)):
                _attach_transport_evidence(
                    error,
                    transport_status_code=response.status_code,
                    transport_headers=response.headers,
                )
            normalized = normalize_upstream_response_error(error, response)
            if normalized is not None:
                raise normalized from error
            raise
        finally:
            try:
                await response.aclose()
            except BaseException as cleanup:
                if primary is None:
                    raise normalize_upstream_cleanup_error(cleanup, response) from cleanup
                primary.add_note(
                    f"upstream response cleanup failed: {type(cleanup).__qualname__}"
                )

    @staticmethod
    def _append_event(
        line: bytes,
        events: list[dict[str, Any]],
    ) -> None:
        data = line.strip()
        if not data or data in {b"[DONE]"} or data.startswith(b":"):
            return
        try:
            loaded = cast(object, orjson.loads(data))
        except orjson.JSONDecodeError:
            return
        if isinstance(loaded, dict):
            events.append(cast(dict[str, Any], loaded))

    async def _post_lifecycle(
        self,
        path: str,
        payload: Mapping[str, Any],
    ) -> bool:
        request = self._http.build_request(
            "POST",
            f"{self._base_url}{path}",
            headers=self._headers(stream=False, session_id="", lifecycle=True),
            content=dumps(dict(payload)),
        )
        try:
            response = await self._http.send(request, stream=False)
            successful = response.is_success
            if not successful:
                logger.warning("Command Code lifecycle request %s returned %s", path, response.status_code)
            await response.aclose()
            return successful
        except Exception as error:
            logger.warning("Command Code lifecycle request %s failed: %s", path, error)
            return False

    async def ensure_initialized(self) -> None:
        if not self._config.initialize_upstream:
            return
        now = time.monotonic()
        if now < self._next_initialization_at:
            return
        async with self._initialization_lock:
            now = time.monotonic()
            if now < self._next_initialization_at:
                return
            initialized = await asyncio.gather(
                self._post_lifecycle(FINGERPRINT_PATH, self._fingerprint),
                self._post_lifecycle(
                    LIFECYCLE_PATH,
                    {
                        "eventType": "cli_session_exists",
                        "metadata": {
                            "sessionId": f"sess_{secrets.token_hex(8)}",
                            "cliVersion": self._config.command_code_version,
                            "mode": "interactive",
                            "os": "linux-x64",
                        },
                    },
                ),
            )
            if all(initialized):
                self._next_initialization_at = time.monotonic() + 8 * 60 * 60
            else:
                # A failed best-effort request is not an eight-hour success.
                # Retry on the next inference request without blocking it.
                self._next_initialization_at = (
                    time.monotonic() + INITIALIZATION_RETRY_DELAY
                )

    async def send(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool,
        extra_headers: Mapping[str, str] | None = None,
        interaction_id: str | None = None,
    ) -> httpx2.Response:
        await self.ensure_initialized()
        body = dict(payload)
        params = body.get("params")
        prompt_cache_key = body.get("prompt_cache_key")
        if isinstance(params, Mapping) and not isinstance(prompt_cache_key, str):
            prompt_cache_key = cast(Mapping[str, Any], params).get("prompt_cache_key")
        session_id = (
            interaction_id
            or (prompt_cache_key if isinstance(prompt_cache_key, str) and prompt_cache_key else None)
            or self._default_session_id
        )
        if isinstance(params, Mapping):
            prepared_params = dict(cast(Mapping[str, Any], params))
            prepared_params["stream"] = True
            if (
                self._config.empty_system_placeholder
                and not prepared_params.get("system")
            ):
                prepared_params["system"] = " "
            body["params"] = prepared_params
        request = self._http.build_request(
            "POST",
            f"{self._base_url}{GENERATE_PATH}",
            headers=self._headers(
                stream=True,
                session_id=session_id,
                extra_headers=extra_headers,
            ),
            content=dumps(body),
        )
        return await self._send_response(request, stream=stream)

    async def fetch_models(self) -> dict[str, Any]:
        request = self._http.build_request(
            "GET",
            f"{self._base_url}{MODELS_PATH}",
            headers=self._headers(
                stream=False,
                session_id=self._default_session_id,
                include_zdr=False,
            ),
        )
        try:
            with activate_pending_upstream_capture():
                observe_active_upstream_request(request)
                response = await self._http.send(request, stream=False)
        except BaseException as error:
            normalized = normalize_upstream_error(error)
            if normalized is None:
                raise
            raise normalized from error
        if not response.is_success:
            try:
                raise upstream_error_from_response(response)
            finally:
                await response.aclose()
        try:
            loaded = cast(object, response.json())
        finally:
            await response.aclose()
        if not isinstance(loaded, dict):
            raise ValueError("Command Code models response must be an object")
        return cast(dict[str, Any], loaded)
