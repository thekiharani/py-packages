"""Error hierarchy shared across SendKit providers and transport."""

from __future__ import annotations


class SendKitError(Exception):
    """Base class for every error raised by SendKit."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "SENDKIT_ERROR",
        cause: BaseException | None = None,
        details: object = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details
        if cause is not None:
            self.__cause__ = cause


class ConfigurationError(SendKitError):
    """Raised when client configuration or required input is missing/invalid."""

    def __init__(
        self,
        message: str,
        *,
        cause: BaseException | None = None,
        details: object = None,
    ) -> None:
        super().__init__(message, code="CONFIGURATION_ERROR", cause=cause, details=details)


class TimeoutError(SendKitError):  # noqa: A001 - mirrors the public SendKit error name
    """Raised when a request exceeds its timeout."""

    def __init__(
        self,
        message: str,
        *,
        cause: BaseException | None = None,
        details: object = None,
    ) -> None:
        super().__init__(message, code="TIMEOUT_ERROR", cause=cause, details=details)


class NetworkError(SendKitError):
    """Raised when the underlying transport fails before a response is received."""

    def __init__(
        self,
        message: str,
        *,
        cause: BaseException | None = None,
        details: object = None,
    ) -> None:
        super().__init__(message, code="NETWORK_ERROR", cause=cause, details=details)


class ApiError(SendKitError):
    """Raised when an HTTP response has a non-2xx status."""

    def __init__(
        self,
        message: str,
        *,
        status: int,
        response_body: object = None,
        cause: BaseException | None = None,
        details: object = None,
    ) -> None:
        super().__init__(message, code="API_ERROR", cause=cause, details=details)
        self.status = status
        self.response_body = response_body


class ProviderError(SendKitError):
    """Raised when a provider accepts the HTTP call but reports a logical failure."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        error_code: str | None = None,
        error_description: str | None = None,
        response_body: object = None,
        cause: BaseException | None = None,
        details: object = None,
    ) -> None:
        super().__init__(message, code="PROVIDER_ERROR", cause=cause, details=details)
        self.provider = provider
        self.error_code = error_code
        self.error_description = error_description
        self.response_body = response_body


class WebhookVerificationError(SendKitError):
    """Raised when an inbound webhook fails signature verification."""

    def __init__(
        self,
        message: str,
        *,
        cause: BaseException | None = None,
        details: object = None,
    ) -> None:
        super().__init__(message, code="WEBHOOK_VERIFICATION_ERROR", cause=cause, details=details)
