from typing import Annotated

from fastapi import Header


async def require_client_headers(
    x_platform: Annotated[str, Header(min_length=1, max_length=20, examples=["android"])],
    x_device: Annotated[str, Header(min_length=1, max_length=100, examples=["Pixel 7"])],
    x_app_version: Annotated[str, Header(min_length=1, max_length=20, examples=["1.0.0"])],
) -> None:
    """Every app action must say which platform, device and app version sent it (subject V.6).

    Declared as a dependency so Swagger shows the three fields; the values themselves
    are logged by RequestLogMiddleware."""
