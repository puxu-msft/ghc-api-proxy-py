"""Turn one CodeBuddy upstream response into the pipeline's closed error set.

The vocabulary and the retryable-status set are the shared normalizer's
(`model_provider.upstream_errors`), imported rather than copied: two normalizers
answering "what does a failed upstream response mean" differently is how one
failure gets two fates depending on which provider served it. This client speaks raw
`httpx2` rather than going through an SDK, so the mapping is written against
responses rather than SDK exceptions.
"""

import httpx2

from app.model_provider.upstream_errors import RETRYABLE_STATUSES, retry_after_seconds
from app.pipeline.exceptions import UpstreamError, UpstreamRateLimit, UpstreamRejected


def upstream_error_from(
    response: httpx2.Response,
) -> UpstreamError | UpstreamRateLimit | UpstreamRejected:
    """Classify one non-200 response the same way the Copilot client's SDK errors are."""
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
    if 400 <= status < 500 and status not in RETRYABLE_STATUSES:
        # A rejected body is as large as the conversation that produced it, so the
        # sent bytes are read only here, the one classification that reports them.
        sent = b""
        request = getattr(response, "request", None)
        if request is not None:
            try:
                content = request.content
            except Exception:
                # `httpx.Request.content` raises for a body that was never read; no
                # send on this path streams, but a classification failure must not
                # replace upstream's verdict with a traceback.
                content = b""
            sent = content if isinstance(content, bytes) else b""
        return UpstreamRejected(
            f"upstream rejected the request: {status}",
            status_code=status,
            headers=headers,
            body=response.text,
            body_bytes=response.content,
            content_type=headers.get("content-type", ""),
            sent=sent,
            body_observed=True,
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
