class CinderError(Exception):
    """Base exception for Cinder framework errors.

    Raised in hooks or routes to return a structured JSON error response.
    Caught by ErrorHandlerMiddleware in the pipeline.
    """

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)

    @classmethod
    def cancel_delete(cls) -> "CinderError":
        """Sentinel error used in before_delete hooks to cancel the delete
        after handling it manually (e.g. soft delete)."""
        return cls(200, "__cancel_delete__")
