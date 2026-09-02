from __future__ import annotations

from typing import Any

from fastapi import status


class APIError(Exception):
    """Base for every error we raise deliberately.

    Carries a stable machine-readable `code` so the frontend can branch on it
    without string-matching human-facing messages.
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "Request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(APIError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthenticated"
    message = "Not authenticated."


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"
    # Deliberately identical for unknown-email and wrong-password so the
    # endpoint cannot be used to enumerate who works at a shop.
    message = "Incorrect email or password."


class AccountLockedError(AuthenticationError):
    code = "account_locked"
    message = "Too many failed attempts. Try again later."


class PermissionDeniedError(APIError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"
    message = "You do not have permission to perform this action."


class TenantInactiveError(APIError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "tenant_inactive"
    message = "This shop is suspended. Contact support."


class SubscriptionRequiredError(APIError):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    code = "subscription_required"
    message = "An active subscription is required."


class QuotaExceededError(APIError):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    code = "quota_exceeded"
    message = "Your plan's limit has been reached."


class NotFoundError(APIError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "Resource not found."


class ConflictError(APIError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "Resource already exists."


class TenantResolutionError(APIError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "tenant_not_found"
    message = "Unknown shop."
