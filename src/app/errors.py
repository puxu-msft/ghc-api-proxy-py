from enum import StrEnum


class ErrorCategory(StrEnum):
    CLIENT = "client"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    NETWORK = "network"
    UPSTREAM = "upstream"
    INTERNAL = "internal"


WIRE_TYPES = {
    ErrorCategory.CLIENT: "invalid_request_error",
    ErrorCategory.AUTH: "authentication_error",
    ErrorCategory.RATE_LIMIT: "rate_limit_error",
    ErrorCategory.NETWORK: "network_error",
    ErrorCategory.UPSTREAM: "upstream_error",
    ErrorCategory.INTERNAL: "internal_error",
}


class ApiError(Exception):
    def __init__(
        self,
        message: str,
        *,
        category: ErrorCategory | None = None,
        status_code: int = 500,
        code: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.category = category or _category_from_status(status_code)
        self.code = code
        self.request_id = request_id

    @property
    def wire_type(self) -> str:
        return WIRE_TYPES[self.category]


def _category_from_status(status_code: int) -> ErrorCategory:
    if status_code in (401, 403):
        return ErrorCategory.AUTH
    if status_code == 429:
        return ErrorCategory.RATE_LIMIT
    if 400 <= status_code < 500:
        return ErrorCategory.CLIENT
    if 500 <= status_code < 600:
        return ErrorCategory.UPSTREAM
    return ErrorCategory.INTERNAL


def classify_error(error: BaseException) -> ErrorCategory:
    if isinstance(error, ApiError):
        return error.category
    if isinstance(error, (ConnectionError, TimeoutError)):
        return ErrorCategory.NETWORK
    return ErrorCategory.INTERNAL