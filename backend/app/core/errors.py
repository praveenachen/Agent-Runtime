from enum import StrEnum


class ErrorCode(StrEnum):
    validation = "ValidationError"
    unavailable = "ProviderUnavailable"
    rate_limited = "ProviderRateLimited"
    provider_timeout = "ProviderTimeout"
    structured_output = "StructuredOutputInvalid"
    execution_timeout = "ExecutionTimeout"
    cancelled = "ExecutionCancelled"
    internal = "InternalExecutionError"


MESSAGES = {
    ErrorCode.validation: "Request or provider configuration is invalid.",
    ErrorCode.unavailable: "Provider is unavailable.",
    ErrorCode.rate_limited: "Provider rate limit reached.",
    ErrorCode.provider_timeout: "Provider request timed out.",
    ErrorCode.structured_output: "Provider output does not match the required schema.",
    ErrorCode.execution_timeout: "Execution deadline exceeded; external outcome may be unknown.",
    ErrorCode.cancelled: "Execution cancelled; an in-flight external request may still complete.",
    ErrorCode.internal: "Execution failed unexpectedly.",
}
RETRYABLE = {ErrorCode.unavailable, ErrorCode.rate_limited, ErrorCode.provider_timeout}


class ExecutionError(Exception):
    """Safe public errors. Never persist raw SDK exceptions or validation inputs."""

    def __init__(self, code: ErrorCode):
        self.code = code
        self.retryable = code in RETRYABLE
        super().__init__(MESSAGES[code])

    def as_dict(self) -> dict:
        return {"code": self.code.value, "message": str(self), "retryable": self.retryable}
