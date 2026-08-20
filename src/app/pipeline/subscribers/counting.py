"""The mark that says this request is being measured rather than sent.

`attempt.prepare` runs on both legs of the same shape: the request that goes to upstream, and the count that reports how large it would be. Nearly every subscriber wants to behave identically on both — a count that ignored the repairs the outbound body gets would answer about a different request than the one that would be asked.

The exception is refusal. A subscriber that refuses a request this endpoint cannot serve is protecting the client from a reply it would otherwise have to trust; on the counting leg there is no reply, so there is nothing to protect and nothing to be misled by. Refusing there converts a question that has an answer into an error.

Kept in `extras` rather than added to `RequestContext`, and in its own module rather than beside one of the subscribers that reads it: it belongs to no single one of them, and importing it from a peer would make that peer look like its owner.
"""

COUNTING_ONLY = "counting_only"
