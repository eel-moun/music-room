"""Small helpers shared by the event / playlist routers."""

import uuid

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession


async def row_exists(session: AsyncSession, model, **filters: uuid.UUID) -> bool:
    clauses = [getattr(model, k) == v for k, v in filters.items()]
    return bool(await session.scalar(select(exists().where(*clauses))))
