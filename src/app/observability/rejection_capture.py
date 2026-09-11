"""Compatibility shim for the retired always-on rejection-body capture."""

from __future__ import annotations

import logging

from app.pipeline.exceptions import UpstreamRejected
from app.pipeline.request import RequestContext

logger = logging.getLogger(__name__)


def capture_rejection(
    context: RequestContext,
    error: BaseException,
    *,
    request_id: str = "",
) -> None:
    """Do not persist an unmatched rejection body.

    Rejection bodies are now part of the conditional CBOR capture only. The
    parameters remain as a compatibility seam for callers outside the active
    request path, but they intentionally have no persistence side effect.
    """
    del context, request_id
    if isinstance(error, UpstreamRejected):
        logger.debug("unmatched upstream rejection body was not captured")


__all__ = ["capture_rejection"]
