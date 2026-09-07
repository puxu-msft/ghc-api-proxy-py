"""Normalize raw OpenAI-compatible HTTP responses into pipeline errors."""

import httpx2

from app.model_provider.upstream_errors import RETRYABLE_STATUSES, retry_after_seconds
from app.pipeline.exceptions import UpstreamError, UpstreamRateLimit, UpstreamRejected


def upstream_error_from_response(
    response: httpx2.Response,
) -> UpstreamError | UpstreamRateLimit | UpstreamRejected:
    headers = {str(key): str(value) for key, value in response.headers.items()}
    status = response.status_code
    if status == 429:
        return UpstreamRateLimit(
            f"upstream rate limited: {status}",
            retry_after=retry_after_seconds(headers),
            headers=headers,
            body=response.text,
            body_bytes=response.content,
            content_type=headers.get("content-type", ""),
            body_observed=True,
        )
    if status not in RETRYABLE_STATUSES and 400 <= status < 500:
        request = response.request
        sent = request.content
        return UpstreamRejected(
            f"upstream rejected the request: {status}",
            status_code=status,
            headers=headers,
            body=response.text,
            body_bytes=response.content,
            content_type=headers.get("content-type", ""),
            body_observed=True,
            sent=sent,
        )
    return UpstreamError(
        f"upstream returned {status}",
        status_code=status,
        headers=headers,
        body=response.text,
        body_bytes=response.content,
        content_type=headers.get("content-type", ""),
        body_observed=True,
    )
