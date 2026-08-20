from app.errors import ApiError, ErrorCategory, classify_error
from app.models.capabilities import ModelCapabilities, ModelSupports
from app.models.common import ErrorResponse, ModelInfo, Usage


def test_usage_model_unknown_fields() -> None:
    usage = Usage.model_validate(
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "unknown_field": "keep_me",
        }
    )

    assert usage.total_tokens == 120
    assert usage.model_extra == {"unknown_field": "keep_me"}
    assert usage.model_dump()["unknown_field"] == "keep_me"


def test_model_capabilities_preserve_unknown_nested_fields() -> None:
    capabilities = ModelCapabilities.model_validate(
        {
            "supports": {"streaming": True, "future_capability": "kept"},
            "future_section": {"enabled": True},
        }
    )

    assert capabilities.supports.model_extra == {"future_capability": "kept"}
    assert capabilities.model_extra == {"future_section": {"enabled": True}}


def test_model_info_preserves_catalog_metadata() -> None:
    model = ModelInfo.model_validate(
        {
            "id": "claude-test",
            "name": "Claude Test",
            "capabilities": {"supports": {"tool_calls": True}},
            "supported_endpoints": ["/v1/messages"],
            "request_headers": {"x-model-route": "a"},
            "vendor_extension": 42,
        }
    )

    assert model.capabilities.supports.tool_calls is True
    assert model.supported_endpoints == ["/v1/messages"]
    assert model.request_headers == {"x-model-route": "a"}
    assert model.model_extra == {"vendor_extension": 42}


def test_error_response_serializes_api_error() -> None:
    error = ApiError(
        message="upstream unavailable",
        category=ErrorCategory.UPSTREAM,
        status_code=503,
        code="upstream_unavailable",
        request_id="req-1",
    )

    response = ErrorResponse.from_api_error(error)

    assert response.model_dump() == {
        "error": {
            "type": "upstream_error",
            "message": "upstream unavailable",
            "code": "upstream_unavailable",
            "request_id": "req-1",
        }
    }


def test_classify_error_maps_status_and_connection_failures() -> None:
    assert classify_error(ApiError("bad input", status_code=400)) is ErrorCategory.CLIENT
    assert classify_error(ApiError("limited", status_code=429)) is ErrorCategory.RATE_LIMIT
    assert classify_error(ApiError("bad gateway", status_code=502)) is ErrorCategory.UPSTREAM
    assert classify_error(ConnectionError("reset")) is ErrorCategory.NETWORK


def test_model_supports_accepts_future_attributes() -> None:
    supports = ModelSupports.model_validate({"future_flag": True})

    assert supports.model_extra == {"future_flag": True}
