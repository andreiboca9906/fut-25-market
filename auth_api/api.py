"""Authentication API endpoints using Django Ninja."""

import logging

from ninja import Router
from ninja.errors import HttpError

from auth_api.services import FutClient
from core.constants import AppVersion, Platform
from core.exceptions import (
    APIError,
    AuthenticationError,
    RateLimitError,
    TwoFactorCodeRequiredError,
)
from core.fut_models.auth import LoginDetails

from .schemas import LoginRequest, LoginResponse, LoginWith2FARequest

logger = logging.getLogger(__name__)
router = Router()


class SimpleTwoFactorProvider:
    """Simple two-factor code provider that uses provided code."""

    def __init__(self, code: str):
        self.code = code

    async def get_code(self) -> str:
        return self.code


@router.post("/login", response=LoginResponse)
async def login(request, data: LoginRequest):
    """Authenticate user with EA servers."""
    try:
        login_details = LoginDetails(
            email=data.email,
            password=data.password,
            platform=Platform(data.platform),
            app_version=AppVersion(data.app_version),
            secret_answer=data.secret_answer,
        )

        async with FutClient(x_ut_sid=data.x_ut_sid) as client:
            try:
                response = await client.login(login_details)

                return LoginResponse(
                    session_id=response.session_id,
                    nucleus_id=response.nucleus_id,
                    persona_id=response.persona_id,
                    dob=response.dob,
                    email=response.email,
                    country=response.country,
                )

            except TwoFactorCodeRequiredError:
                raise HttpError(400, "Two-factor authentication code required")

    except TwoFactorCodeRequiredError:
        raise HttpError(400, "Two-factor authentication code required")
    except AuthenticationError as e:
        logger.error(f"Authentication failed: {e}")
        raise HttpError(401, f"Authentication failed: {str(e)}")
    except RateLimitError as e:
        logger.error(f"Rate limit exceeded: {e}")
        raise HttpError(429, "Rate limit exceeded. Please try again later.")
    except APIError as e:
        logger.error(f"API error during login: {e}")
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error during login: {e}")
        raise HttpError(500, "An unexpected error occurred")


@router.post("/login-with-2fa", response=LoginResponse)
async def login_with_2fa(request, data: LoginWith2FARequest):
    """Authenticate user with EA servers using two-factor authentication."""
    try:
        login_details = LoginDetails(
            email=data.email,
            password=data.password,
            platform=Platform(data.platform),
            app_version=AppVersion(data.app_version),
            secret_answer=data.secret_answer,
        )

        two_factor_provider = SimpleTwoFactorProvider(data.two_factor_code)

        async with FutClient(x_ut_sid=data.x_ut_sid) as client:
            response = await client.login(
                login_details,
                two_factor_provider=two_factor_provider
            )

            return LoginResponse(
                session_id=response.session_id,
                nucleus_id=response.nucleus_id,
                persona_id=response.persona_id,
                dob=response.dob,
                email=response.email,
                country=response.country,
            )

    except AuthenticationError as e:
        logger.error(f"Authentication failed: {e}")
        raise HttpError(401, f"Authentication failed: {str(e)}")
    except RateLimitError as e:
        logger.error(f"Rate limit exceeded: {e}")
        raise HttpError(429, "Rate limit exceeded. Please try again later.")
    except APIError as e:
        logger.error(f"API error during login: {e}")
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error during login: {e}")
        raise HttpError(500, "An unexpected error occurred")
