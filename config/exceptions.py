"""Domain errors with stable HTTP mappings."""


class AppError(Exception):
    """Base application error. API handlers serialize `code` and `status_code`."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        code: str = "internal_error",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404, code="not_found")


class ValidationError(AppError):
    """Invalid input for a persistence operation (missing/out-of-range fields)."""

    def __init__(self, message: str = "Invalid lead data") -> None:
        super().__init__(message, status_code=422, code="validation_error")


class CollectorError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400, code="collector_error")


class PipelineError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=500, code="pipeline_error")
