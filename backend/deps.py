"""FastAPI dependencies for TabSage.

The BYOK key dependency reads the user's provider key from the `X-Provider-Key`
request header. It is returned to the caller for transient in-memory use only and
must NEVER be logged, stored, or read from server config.

Implemented via `APIKeyHeader` so Swagger renders an **Authorize** button: enter
the key once in `/docs` and it is attached to every secured request, instead of
retyping it into a header field per call.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

# auto_error=False so we return TabSage's own friendly 401 message rather than
# FastAPI's generic "Not authenticated".
_api_key_header = APIKeyHeader(name="X-Provider-Key", auto_error=False)


async def get_provider_key(
    api_key: Annotated[str | None, Depends(_api_key_header)] = None,
) -> str:
    """Extract and validate the per-request provider key.

    Raises 401 if the header is missing or blank. The returned value is used
    transiently to call the provider and is never persisted.
    """
    if not api_key or not api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Missing X-Provider-Key header. TabSage is BYOK: send your "
                "provider key with each request."
            ),
        )
    return api_key.strip()
