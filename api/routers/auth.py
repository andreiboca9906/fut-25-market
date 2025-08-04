"""Authentication endpoints."""

from fastapi import APIRouter, HTTPException, Request, status

from fut_toolkit.exceptions import (
    APIError,
    AuthenticationError,
    RateLimitError,
    TwoFactorCodeRequiredError,
)
from fut_toolkit.models.auth import LoginDetails
from fut_toolkit.services.fut_client import FutClient

from ..schemas import LoginRequest, LoginResponseSchema

router = APIRouter(prefix="/auth", tags=["Authentication"])


class SimpleTwoFactorProvider:
    """Simple two-factor code provider that uses provided code."""
    
    def __init__(self, code: str):
        self.code = code
        
    async def get_code(self) -> str:
        return self.code


@router.post("/login", response_model=LoginResponseSchema)
async def login(request: Request, login_data: LoginRequest):
    """Authenticate user with EA servers."""
    try:
        login_details = LoginDetails(
            email=login_data.email,
            password=login_data.password,
            platform=login_data.platform,
            app_version=login_data.app_version,
            secret_answer=login_data.secret_answer
        )
        
        async with FutClient(x_ut_sid=login_data.x_ut_sid) as client:
            try:
                response = await client.login(login_details)
                
                # Store session cookies in request state for potential reuse
                if hasattr(request.state, "cookies"):
                    request.state.cookies = client.session.cookies
                    
                return LoginResponseSchema(
                    session_id=response.session_id,
                    nucleus_id=response.nucleus_id,
                    persona_id=response.persona_id,
                    dob=response.dob,
                    email=response.email,
                    country=response.country
                )
                
            except TwoFactorCodeRequiredError:
                raise HTTPException(
                    status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                    detail="Two-factor authentication code required. Include 'two_factor_code' in request."
                )
                
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except RateLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e)
        )
    except APIError as e:
        raise HTTPException(
            status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/login-with-2fa", response_model=LoginResponseSchema)
async def login_with_two_factor(
    request: Request,
    login_data: LoginRequest,
    two_factor_code: str
):
    """Authenticate user with two-factor code."""
    try:
        login_details = LoginDetails(
            email=login_data.email,
            password=login_data.password,
            platform=login_data.platform,
            app_version=login_data.app_version,
            secret_answer=login_data.secret_answer
        )
        
        two_factor_provider = SimpleTwoFactorProvider(two_factor_code)
        
        async with FutClient(x_ut_sid=login_data.x_ut_sid) as client:
            response = await client.login(login_details, two_factor_provider)
            
            # Store session cookies
            if hasattr(request.state, "cookies"):
                request.state.cookies = client.session.cookies
                
            return LoginResponseSchema(
                session_id=response.session_id,
                nucleus_id=response.nucleus_id,
                persona_id=response.persona_id,
                dob=response.dob,
                email=response.email,
                country=response.country
            )
            
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except RateLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e)
        )
    except APIError as e:
        raise HTTPException(
            status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
