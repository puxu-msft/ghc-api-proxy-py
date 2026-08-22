"""Where the ASGI app keeps the object graph, and how a route asks for it.

One module because it was two: `CHAIN_STATE_KEY` and the accessor were declared identically in `pipeline_app` and in `ops_routes`, and a constant spelled twice is a constant that can come to disagree — the routes would then read a key the factory never wrote, and every request would fail on an attribute that is simply absent.

Deliberately tiny and importing almost nothing. Both route modules and the factory need it, so anything heavier here would be dragged into all three.
"""

from typing import cast

from fastapi import FastAPI, Request

from app.core.chain import Chain

CHAIN_STATE_KEY = "pipeline_chain"


def set_chain(app: FastAPI, chain: Chain) -> None:
    """Put the chain where `chain_of` will look for it."""
    setattr(app.state, CHAIN_STATE_KEY, chain)


def chain_of(request: Request) -> Chain:
    """The chain this request is served from."""
    return cast(Chain, getattr(request.app.state, CHAIN_STATE_KEY))


def chain_of_app(app: FastAPI) -> Chain:
    """The chain outside a request — the lifespan has an app but no request to read it off."""
    return cast(Chain, getattr(app.state, CHAIN_STATE_KEY))
