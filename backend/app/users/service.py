import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.policies.profile import Relation
from app.users.models import Friendship, FriendshipStatus


def pair_filter(a: uuid.UUID, b: uuid.UUID):
    return or_(
        and_(Friendship.requester_id == a, Friendship.addressee_id == b),
        and_(Friendship.requester_id == b, Friendship.addressee_id == a),
    )


async def friendship_between(
    session: AsyncSession, a: uuid.UUID, b: uuid.UUID
) -> Friendship | None:
    return await session.scalar(select(Friendship).where(pair_filter(a, b)))


async def are_friends(session: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> bool:
    friendship = await friendship_between(session, a, b)
    return friendship is not None and friendship.status is FriendshipStatus.accepted


async def relation(session: AsyncSession, viewer: uuid.UUID, other: uuid.UUID) -> Relation:
    if viewer == other:
        return Relation.self
    return Relation.friend if await are_friends(session, viewer, other) else Relation.other
