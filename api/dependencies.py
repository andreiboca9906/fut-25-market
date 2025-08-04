"""API dependencies and utilities."""

from typing import Optional

from fastapi import Header, HTTPException, status

from fut_toolkit.services.fut_client import FutClient


def get_fut_client(x_ut_sid: Optional[str] = Header(None, alias="x-ut-sid"), rotate_ua: bool = True) -> FutClient:
    """Get FutClient with session ID from headers."""
    if not x_ut_sid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-UT-SID header. Please provide session ID."
        )

    return FutClient(x_ut_sid=x_ut_sid, rotate_ua=rotate_ua)


def get_optional_fut_client(
    x_ut_sid: Optional[str] = Header(None, alias="x-ut-sid"), rotate_ua: bool = True
) -> FutClient:
    """Get FutClient with optional session ID from headers."""
    return FutClient(x_ut_sid=x_ut_sid, rotate_ua=rotate_ua)
