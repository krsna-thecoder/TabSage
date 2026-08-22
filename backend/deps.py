"""FastAPI dependencies for TabSage.

The BYOK key dependency reads the user's provider key from the `X-Provider-Key`
request header. It is returned to the caller for transient in-memory use only and
must NEVER be logged, stored, or read from server config.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException, status


async def get_provider_key(
    x_provider_key: Annotated[str | None, Header(alias="X-Provider-Key")] = None,
) -> str:
    """Extract and validate the per-request provider key.

    Raises 401 if the header is missing or blank. The returned value is used
    transiently to call the provider and is never persisted.
    """
    if not x_provider_key or not x_provider_key.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Missing X-Provider-Key header. TabSage is BYOK: send your "
                "provider key with each request."
            ),
        )
    return x_provider_key.strip()
