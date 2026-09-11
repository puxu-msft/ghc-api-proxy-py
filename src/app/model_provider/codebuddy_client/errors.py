"""Turn one CodeBuddy upstream response into the pipeline's closed error set.

The vocabulary and the retryable-status set are the shared normalizer's
(`model_provider.upstream_errors`), imported rather than copied: two normalizers
answering "what does a failed upstream response mean" differently is how one
failure gets two fates depending on which provider served it. This client speaks raw
`httpx2` rather than going through an SDK, so the mapping is written against
responses rather than SDK exceptions.
"""

import httpx2

from app.model_provider.upstream_errors import (
    RETRYABLE_STATUSES,
    response_body_evidence,
    response_body_text,
    retry_after_seconds,
    sent_body_evidence_from_error,
)
from app.pipeline.exceptions import UpstreamError, UpstreamRateLimit, UpstreamRejected


def upstream_error_from(
    response: httpx2.Response,
) -> UpstreamError | UpstreamRateLimit | UpstreamRejected:
    """Classify one non-200 response the same way the Copilot client's SDK errors are."""
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
    if 400 <= status < 500 and status not in RETRYABLE_STATUSES:
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
