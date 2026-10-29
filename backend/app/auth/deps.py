from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.db import SessionDep
from app.core.errors import api_error
from app.core.security import decode_access_token
from app.users.models import User

_bearer = HTTPBearer(auto_error=False)


async def current_user(
    request: Request,
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    user_id = decode_access_token(credentials.credentials) if credentials else None
    user = await session.get(User, user_id) if user_id else None
    if user is None:
        raise api_error(401, "not_authenticated", "Missing or invalid access token")
    request.state.user_id = str(user.id)  # picked up by the request log middleware
    return user


CurrentUser = Annotated[User, Depends(current_user)]
