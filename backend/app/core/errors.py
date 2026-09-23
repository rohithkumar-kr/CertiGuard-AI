"""Application-level exceptions with user-safe messages.

Messages returned to users must never expose stack traces or internals.
"""


class AppError(Exception):
    """Base error with a safe, human-readable message."""

    status_code = 400
    message = "Something went wrong."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.message
        super().__init__(self.message)


class FileValidationError(AppError):
    status_code = 400
    message = "The uploaded file is not valid."


class FileTooLargeError(FileValidationError):
    message = "The uploaded file is too large."


class ProcessingError(AppError):
    status_code = 422
    message = "The document could not be processed."


class ModelUnavailableError(AppError):
    status_code = 503
    message = "The verification model is not available right now. Please try again later."


class DatabaseError(AppError):
    status_code = 500
    message = "Could not store the verification result."