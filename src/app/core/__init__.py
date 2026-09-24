"""Facts shared across domains, owned by none of them.

This package holds the assembly record (`chain.py`) that `server`, `pipeline` and
`debug` all read. The generation/release id parsers used to live here for the same
reason, but their only live consumer proved to be `tokenization.snapshot_store`,
so they moved to `app.tokenization` — keeping them here for one consumer would
have kept `tokenization` depending on `core` for no reason.
"""
