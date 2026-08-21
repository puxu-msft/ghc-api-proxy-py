"""The counters `/metrics` answers with.

`prometheus_client`'s default `REGISTRY` is what `ops_routes.metrics` serialises, so a counter defined here is exported by being defined — there is nothing to register and nothing to wire. That is also why they live in one module: a metric declared beside the code that increments it is invisible until that code is imported, and a metric nobody can find is a metric nobody reads.

Deliberately not `app.observability.telemetry`. That module builds an OpenTelemetry meter provider and is only ever constructed by the legacy `app_factory`; going through it would pull four `opentelemetry-*` packages into a path that today imports none of them, to reach the same Prometheus endpoint.

Counts rather than the detail: a count says how often, and the per-request record says which fields on which request. Both are needed and neither substitutes — the count is what shows a translation quietly dropping a parameter on every request, and the record is what says which parameter.
"""

from prometheus_client import Counter

# Labelled by direction and code rather than by model or request, because a metric's label set multiplies its series count and a request id would make one series per request. Which request lost what is the record's question; this answers how often it happens at all.
TRANSLATION_LOSSES = Counter(
    "ghc_proxy_translation_losses_total",
    "Fields a translation could not carry, by crossing direction and loss code.",
    ("direction", "code"),
)

# Unlabelled: there is one reason this fires and one thing it removes. A counter rather than a log line because it fires on every request from the client that sends it — a per-request INFO would be noise, while a number that climbs in step with the request count is exactly the right shape for something that is supposed to be routine.
ATTRIBUTION_LINES_STRIPPED = Counter(
    "ghc_proxy_attribution_lines_stripped_total",
    "Client-injected attribution lines removed from an inbound Anthropic system prompt.",
)
