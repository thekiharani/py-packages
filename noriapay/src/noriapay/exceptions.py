from __future__ import annotations


class NoriapayError(Exception):
    def __init__(
        self, message: str, *, code: str = "NORIAPAY_ERROR", details: object = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


class ConfigurationError(NoriapayError):
    def __init__(self, message: str, *, details: object = None) -> None:
        super().__init__(message, code="CONFIGURATION_ERROR", details=details)


class TimeoutError(NoriapayError):
    def __init__(self, message: str, *, details: object = None) -> None:
        super().__init__(message, code="TIMEOUT_ERROR", details=details)


class NetworkError(NoriapayError):
    def __init__(self, message: str, *, details: object = None) -> None:
        super().__init__(message, code="NETWORK_ERROR", details=details)


class AuthenticationError(NoriapayError):
    def __init__(self, message: str, *, details: object = None) -> None:
        super().__init__(message, code="AUTHENTICATION_ERROR", details=details)


class WebhookVerificationError(NoriapayError):
    def __init__(self, message: str, *, details: object = None) -> None:
        super().__init__(message, code="WEBHOOK_VERIFICATION_ERROR", details=details)


class ApiError(NoriapayError):
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
