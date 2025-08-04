"""Custom exceptions for FIFA Ultimate Team API."""


class FutError(Exception):
    """Base exception for FUT toolkit errors."""


class AuthenticationError(FutError):
    """Authentication failed."""


class SessionExpiredError(FutError):
    """Session has expired."""


class TwoFactorCodeRequiredError(FutError):
    """Two-factor authentication code required."""


class RateLimitError(FutError):
    """API rate limit exceeded."""


class AuctionNotFoundError(FutError):
    """Auction item not found."""


class InsufficientCreditsError(FutError):
    """Not enough credits for operation."""


class APIError(FutError):
    """Generic API error."""
    
    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code
