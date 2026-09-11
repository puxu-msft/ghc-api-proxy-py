from collections.abc import AsyncIterator, Callable

import httpx2
import pytest

from app.model_provider.codebuddy_client.errors import upstream_error_from
from app.model_provider.openai_compatible.errors import upstream_error_from_response
from app.model_provider.upstream_errors import (
    normalize_upstream_response_error,
    read_response_body_with_evidence,
)
from app.pipeline.exceptions import UpstreamError, UpstreamRateLimit, UpstreamRejected

type ErrorNormalizer = Callable[
    [httpx2.Response],
    UpstreamError | UpstreamRateLimit | UpstreamRejected,
]


@pytest.mark.parametrize("status", [429, 500])
@pytest.mark.parametrize(
    "normalize",
    [upstream_error_from, upstream_error_from_response],
)
def test_provider_error_normalizers_keep_sent_request_bytes(
    status: int,
    normalize: ErrorNormalizer,
) -> None:
    sent = b'{"model":"provider-model"}'
    request = httpx2.Request("POST", "https://provider.example/responses", content=sent)
    response = httpx2.Response(status, json={"error": {"message": "failed"}}, request=request)

    error = normalize(response)

    assert error.sent == sent


@pytest.mark.parametrize(
    "normalize",
    [upstream_error_from, upstream_error_from_response],
)
def test_provider_error_normalizers_distinguish_observed_empty_request_from_absence(
    normalize: ErrorNormalizer,
) -> None:
    observed_response = httpx2.Response(
        500,
        json={"error": {"message": "failed"}},
        request=httpx2.Request(
            "POST",
            "https://provider.example/responses",
            content=b"",
        ),
    )
    absent_response = httpx2.Response(500, json={"error": {"message": "failed"}})

    observed = normalize(observed_response)
    absent = normalize(absent_response)

    assert (observed.sent, observed.sent_observed) == (b"", True)
    assert (absent.sent, absent.sent_observed) == (b"", False)


def test_response_error_normalizer_keeps_observed_empty_request_before_fallback() -> None:
    response = httpx2.Response(
        500,
        json={"error": {"message": "failed"}},
        request=httpx2.Request(
            "POST",
            "https://provider.example/response-fallback",
            content=b"response-fallback",
        ),
    )
    observed_empty = normalize_upstream_response_error(
        httpx2.ReadTimeout(
            "slow",
            request=httpx2.Request(
                "POST",
                "https://provider.example/error-request",
                content=b"",
            ),
        ),
        response,
    )
    absent = normalize_upstream_response_error(httpx2.ReadTimeout("slow"), response)

    assert isinstance(observed_empty, UpstreamError)
    assert (observed_empty.sent, observed_empty.sent_observed) == (b"", True)
    assert isinstance(absent, UpstreamError)
    assert (absent.sent, absent.sent_observed) == (b"response-fallback", True)


async def test_partial_status_response_keeps_status_and_body_evidence() -> None:
    class PartialBody(httpx2.AsyncByteStream):
        def __aiter__(self) -> AsyncIterator[bytes]:
            return self._read()

        async def _read(self) -> AsyncIterator[bytes]:
            yield b'{"error":'
            raise httpx2.ReadTimeout("body timeout")

        async def aclose(self) -> None:
            return None

    sent = b'{"model":"provider-model"}'
    request = httpx2.Request("POST", "https://provider.example/responses", content=sent)
    response = httpx2.Response(
        500,
        content=PartialBody(),
        headers={"content-type": "application/json"},
        request=request,
    )

    with pytest.raises(httpx2.ReadTimeout) as raised:
        await read_response_body_with_evidence(response)

    normalized = normalize_upstream_response_error(raised.value, response)

    assert isinstance(normalized, UpstreamError)
    assert normalized.status_code == 500
    assert normalized.sent == sent
    assert normalized.body_observed is True
    assert normalized.body_bytes == b'{"error":'
