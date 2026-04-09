from __future__ import annotations


class NoriaMessagingError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "NORIA_MESSAGING_ERROR",
        details: object = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


class ConfigurationError(NoriaMessagingError):
    def __init__(self, message: str, *, details: object = None) -> None:
        super().__init__(message, code="CONFIGURATION_ERROR", details=details)


class TimeoutError(NoriaMessagingError):
    def __init__(self, message: str, *, details: object = None) -> None:
        super().__init__(message, code="TIMEOUT_ERROR", details=details)


class NetworkError(NoriaMessagingError):
    def __init__(self, message: str, *, details: object = None) -> None:
        super().__init__(message, code="NETWORK_ERROR", details=details)


class ApiError(NoriaMessagingError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        response_body: object = None,
        details: object = None,
    ) -> None:
        super().__init__(message, code="API_ERROR", details=details)
        self.status_code = status_code
        self.response_body = response_body


class GatewayError(NoriaMessagingError):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        error_code: str | None = None,
        error_description: str | None = None,
        response_body: object = None,
        details: object = None,
    ) -> None:
        super().__init__(message, code="GATEWAY_ERROR", details=details)
        self.provider = provider
        self.error_code = error_code
        self.error_description = error_description
        self.response_body = response_body


class WebhookVerificationError(NoriaMessagingError):
    def __init__(self, message: str, *, details: object = None) -> None:
        super().__init__(message, code="WEBHOOK_VERIFICATION_ERROR", details=details)


NoriaSmsError = NoriaMessagingError
