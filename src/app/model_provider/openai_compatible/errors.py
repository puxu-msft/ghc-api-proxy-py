"""Normalize raw OpenAI-compatible HTTP responses into pipeline errors."""

import httpx2

from app.model_provider.upstream_errors import (
    RETRYABLE_STATUSES,
    response_body_evidence,
    response_body_text,
    retry_after_seconds,
    sent_body_evidence_from_error,
)
from app.pipeline.exceptions import UpstreamError, UpstreamRateLimit, UpstreamRejected


def upstream_error_from_response(
    response: httpx2.Response,
) -> UpstreamError | UpstreamRateLimit | UpstreamRejected:
    headers = {str(key): str(value) for key, value in response.headers.items()}
    status = response.status_code
    body_bytes, body_observed = response_body_evidence(response)
    body = response_body_text(response, body_bytes, body_observed)
    sent, sent_observed = sent_body_evidence_from_error(response)
    if status == 429:
        return UpstreamRateLimit(
            f"upstream rate limited: {status}",
            retry_after=retry_after_seconds(headers),
            headers=headers,
            body=body,
            body_bytes=body_bytes,
            content_type=headers.get("content-type", ""),
            sent=sent,
            sent_observed=sent_observed,
            body_observed=body_observed,
        )
    if status not in RETRYABLE_STATUSES and 400 <= status < 500:
        return UpstreamRejected(
            f"upstream rejected the request: {status}",
            status_code=status,
            headers=headers,
            body=body,
            body_bytes=body_bytes,
            content_type=headers.get("content-type", ""),
            sent=sent,
            sent_observed=sent_observed,
            body_observed=body_observed,
        )
    return UpstreamError(
        f"upstream returned {status}",
        status_code=status,
        headers=headers,
        body=body,
        body_bytes=body_bytes,
        content_type=headers.get("content-type", ""),
        sent=sent,
        sent_observed=sent_observed,
        body_observed=body_observed,
    )
