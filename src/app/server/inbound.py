"""Inbound format parsing.

`docs/.human-controlled/api.md` gives the endpoint list, and each one fixes the wire format its body arrives in.
The format is therefore a property of the route rather than something to sniff from the body.

Parsing here stays basic on purpose.
It names the format, the model and whether streaming was asked for; the rest is the pipeline's.
"""

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from app.pipeline.request import RequestContext
from app.pipeline.request_headers import forwarded_client_headers
from app.server.routes.table import InboundRoute


class InboundRequestError(ValueError):
    """The request cannot be turned into a context, so it never reaches the pipeline."""




def build_context(
    route: InboundRoute,
    payload: Mapping[str, Any],
    headers: Mapping[str, str] | None = None,
) -> RequestContext:
    """Turn a parsed body into a RequestContext.

    A missing or non-string model is rejected here rather than downstream.
    Routing cannot fail closed on a capability if it never learned which model to ask about.

    Headers are filtered here rather than at the send site so that nothing downstream ever holds the client's credentials.
    """
    model = payload.get("model")
    if not isinstance(model, str) or not model.strip():
        raise InboundRequestError("request body must carry a non-empty string model")

    stream = bool(payload.get("stream", False))
    if stream and not route.streamable:
        raise InboundRequestError(f"{route.path} does not support streaming")

    context = RequestContext(
        inbound_format=route.wire_format,
        requested_model=model.strip(),
        # Deep rather than shallow, and that is the whole point of the pair. The fixups downstream edit `messages` and `system` in place; with a shallow copy those edits reached the caller's parsed body, so there was no version of the request left that said what the client actually sent.
        payload=deepcopy(dict(payload)),
        original_payload=payload,
        stream=stream,
        client_headers=forwarded_client_headers(headers or {}),
    )
    if route.count_tokens:
        context.extras["count_tokens"] = True
    return context
