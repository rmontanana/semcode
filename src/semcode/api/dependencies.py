"""
Shared FastAPI dependencies (authentication, telemetry).
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from ..settings import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: str = Security(_api_key_header)) -> str | None:
    """
    Enforce optional API-key authentication.

    If ``SEMCODE_API_KEY`` is configured the incoming request must provide the
    matching value in the ``X-API-Key`` header; otherwise the dependency is a
    no-op.
    """
    expected = settings.api_key
    if not expected:
        return None
    if api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )
    return api_key


def telemetry_enabled() -> bool:
    """Expose telemetry toggle as a dependency."""
    return settings.telemetry_enabled
