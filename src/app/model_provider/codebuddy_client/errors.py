"""Compatibility import for the generic provider HTTP error normalizer."""

from app.model_provider.http_errors import upstream_error_from_response

upstream_error_from = upstream_error_from_response

__all__ = ["upstream_error_from"]
