from collections.abc import Callable, Mapping
from time import time
from typing import Any, cast
from uuid import UUID, uuid4

import httpx2

from app.config.schema import XingchenProviderConfig
from app.model_provider.upstream_errors import normalize_upstream_error
from app.model_provider.xingchen.signing import SIGN_VERSION, sign_gateway_request
from app.wire_json import dumps

CHAT_COMPLETIONS_PATH = "/chat/completions"

_PROVIDER_OWNED_HEADERS = frozenset(
    {
        "accept",
        "authorization",
        "cache-control",
        "content-type",
        "user-agent",
        "x-app-version",
        "x-route-target",
        "x-superagent-device-id",
        "x-superagent-install-id",
        "x-superagent-nonce",
        "x-superagent-sign-version",
        "x-superagent-signature",
        "x-superagent-timestamp",
        "x-teleai-client-type",
        "x-teleai-upstream-request-id",
        "x-token",
    }
)
_BLOCKED_TRANSPORT_HEADERS = frozenset({"host", "content-length", "transfer-encoding"})


class XingchenClient:
    def __init__(
        self,
        http_client: httpx2.AsyncClient,
        config: XingchenProviderConfig,
        *,
        clock: Callable[[], float] = time,
        uuid_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._http = http_client
        self._config = config
        self._clock = clock
        self._uuid_factory = uuid_factory
        self._url = f"{config.api_base_url.rstrip('/')}{CHAT_COMPLETIONS_PATH}"

    @property
    def base_url(self) -> str:
        return self._config.api_base_url.rstrip("/")

    @staticmethod
    def _prepare_payload(payload: Mapping[str, Any], *, stream: bool) -> dict[str, Any]:
        prepared = dict(payload)
        if not stream:
            return prepared
        if "stream_options" not in prepared:
            prepared["stream_options"] = {"include_usage": True}
        elif isinstance(prepared["stream_options"], Mapping):
            stream_options = dict(cast(Mapping[str, Any], prepared["stream_options"]))
            stream_options.setdefault("include_usage", True)
            prepared["stream_options"] = stream_options
        prepared.setdefault("tool_stream", True)
        return prepared

    def _upstream_request_id(self, nonce: str) -> str:
        while True:
            candidate = str(self._uuid_factory())
            if candidate != nonce:
                return candidate

    async def send_chat_completions(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        body = dumps(self._prepare_payload(payload, stream=stream))
        request = self._http.build_request("POST", self._url, content=body)
        timestamp = str(int(self._clock()))
        nonce = str(self._uuid_factory())
        signature = sign_gateway_request(
            method=request.method,
            request_uri=request.url.raw_path.decode("ascii"),
            body=body,
            x_token=self._config.x_token,
            install_id=self._config.install_id,
            app_version=self._config.app_version,
            timestamp=timestamp,
            nonce=nonce,
        )

        if extra_headers:
            blocked = _PROVIDER_OWNED_HEADERS | _BLOCKED_TRANSPORT_HEADERS
            for name, value in extra_headers.items():
                if name.lower() not in blocked:
                    request.headers[name] = value

        owned_headers = {
            "Authorization": f"Bearer {self._config.gateway_api_key}",
            "X-Token": self._config.x_token,
            "X-SuperAgent-Sign-Version": SIGN_VERSION,
            "X-SuperAgent-Signature": signature.value,
            "X-SuperAgent-Timestamp": signature.timestamp,
            "X-SuperAgent-Nonce": signature.nonce,
            "X-SuperAgent-Device-Id": self._config.device_id,
            "X-SuperAgent-Install-Id": self._config.install_id,
            "X-App-Version": self._config.app_version,
            "X-Route-Target": self._config.route_target,
            "X-TeleAI-Client-Type": self._config.client_type,
            "X-TeleAI-Upstream-Request-ID": self._upstream_request_id(nonce),
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": self._config.user_agent,
        }
        for name, value in owned_headers.items():
            request.headers[name] = value

        try:
            response = await self._http.send(request, stream=stream)
            if not response.is_success:
                try:
                    if not response.is_stream_consumed:
                        await response.aread()
                    response.raise_for_status()
                finally:
                    await response.aclose()
            return response
        except BaseException as error:
            normalized = normalize_upstream_error(error)
            if normalized is None:
                raise
            raise normalized from error
