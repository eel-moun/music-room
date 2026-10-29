import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.auth.deps import CurrentUser
from app.core.db import SessionDep
from app.core.errors import api_error, not_found
from app.policies.profile import Relation, visible_profile_blocks
from app.realtime.rooms import rooms
from app.users.models import AuthIdentity, Friendship, FriendshipStatus, User
from app.users.schemas import (
    FriendOut,
    FriendRequestIn,
    FriendRequestOut,
    FriendsInfo,
    MeOut,
    MusicPreferences,
    PrivateInfo,
    ProfileOut,
    ProfileUpdate,
    PublicInfo,
    UserSummary,
)
from app.users.service import friendship_between, relation

router = APIRouter(tags=["users"])


def build_profile(user: User, rel: Relation) -> dict:
    blocks = visible_profile_blocks(rel)
    return {
        "id": user.id,
        "display_name": user.display_name,
        "relation": rel.value,
        "public_info": PublicInfo(**user.public_info),
        "music_preferences": MusicPreferences(**user.music_preferences),
        "friends_info": FriendsInfo(**user.friends_info) if "friends_info" in blocks else None,
        "private_info": PrivateInfo(**user.private_info) if "private_info" in blocks else None,
    }


async def build_me(session: SessionDep, user: User) -> MeOut:
    google = await session.scalar(
        select(AuthIdentity.id).where(
            AuthIdentity.user_id == user.id, AuthIdentity.provider == "google"
        )
    )
    return MeOut(
        **build_profile(user, Relation.self),
        email=user.email,
        email_verified=user.email_verified,
        has_password=user.password_hash is not None,
        google_linked=google is not None,
    )


@router.get("/users/me")
async def get_me(user: CurrentUser, session: SessionDep) -> MeOut:
    return await build_me(session, user)


@router.patch("/users/me")
async def update_me(body: ProfileUpdate, user: CurrentUser, session: SessionDep) -> MeOut:
    if body.display_name is not None:
        user.display_name = body.display_name
    for block in ("public_info", "friends_info", "private_info", "music_preferences"):
        value = getattr(body, block)
        if value is not None:
            setattr(user, block, value.model_dump(mode="json"))
    await session.commit()
    return await build_me(session, user)


@router.get("/users")
async def search_users(
    user: CurrentUser,
    session: SessionDep,
    q: Annotated[str, Query(min_length=1, max_length=50)],
) -> list[UserSummary]:
    # Escape LIKE wildcards so "%" in the query is a literal character.
    pattern = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    users = await session.scalars(
        select(User)
        .where(User.display_name.ilike(f"%{pattern}%", escape="\\"), User.id != user.id)
        .order_by(User.display_name)
        .limit(20)
    )
    return [UserSummary.model_validate(u) for u in users]


@router.get("/users/{user_id}")
async def get_profile(user_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> ProfileOut:
    other = await session.get(User, user_id)
    if other is None:
        raise not_found("User")
    return ProfileOut(**build_profile(other, await relation(session, user.id, other.id)))


# --- Friends -----------------------------------------------------------------


@router.get("/friends")
async def list_friends(user: CurrentUser, session: SessionDep) -> list[FriendOut]:
    rows = await session.scalars(
        select(Friendship).where(
            Friendship.status == FriendshipStatus.accepted,
            or_(Friendship.requester_id == user.id, Friendship.addressee_id == user.id),
        )
    )
    friends = []
    for f in rows:
        other_id = f.addressee_id if f.requester_id == user.id else f.requester_id
        other = await session.get(User, other_id)
        assert other is not None
        friends.append(FriendOut(user=UserSummary.model_validate(other), since=f.accepted_at))
    return sorted(friends, key=lambda f: f.user.display_name.lower())


@router.get("/friends/requests")
async def list_friend_requests(user: CurrentUser, session: SessionDep) -> list[FriendRequestOut]:
    rows = await session.scalars(
        select(Friendship)
        .where(
            Friendship.status == FriendshipStatus.pending,
            or_(Friendship.requester_id == user.id, Friendship.addressee_id == user.id),
        )
        .order_by(Friendship.created_at.desc())
    )
    return [await _request_out(session, f, user.id) for f in rows]


async def _request_out(session: SessionDep, f: Friendship, me: uuid.UUID) -> FriendRequestOut:
    incoming = f.addressee_id == me
    other = await session.get(User, f.requester_id if incoming else f.addressee_id)
    assert other is not None
    return FriendRequestOut(
        id=f.id,
        status=f.status,
        direction="incoming" if incoming else "outgoing",
        user=UserSummary.model_validate(other),
        created_at=f.created_at,
    )


@router.post("/friends/requests", status_code=status.HTTP_201_CREATED)
async def send_friend_request(
    body: FriendRequestIn, user: CurrentUser, session: SessionDep
) -> FriendRequestOut:
    if body.user_id == user.id:
        raise api_error(400, "self_request", "You can't befriend yourself")
    if await session.get(User, body.user_id) is None:
        raise not_found("User")

    existing = await friendship_between(session, user.id, body.user_id)
    if existing is not None:
        if existing.status is FriendshipStatus.pending and existing.addressee_id == user.id:
            # They already asked us: sending one back means yes.
            return await _accept(session, existing, user.id)
        raise api_error(409, "already_exists", "A request or friendship already exists")

    friendship = Friendship(requester_id=user.id, addressee_id=body.user_id)
    session.add(friendship)
    try:
        await session.commit()
    except IntegrityError:  # both users clicked "add friend" at the same moment
        await session.rollback()
        raise api_error(409, "already_exists", "A request or friendship already exists") from None
    await rooms.publish(
        f"user:{body.user_id}", "friend.request", {"from": str(user.id), "name": user.display_name}
    )
    return await _request_out(session, friendship, user.id)


@router.post("/friends/requests/{request_id}/accept")
async def accept_friend_request(
    request_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> FriendRequestOut:
    friendship = await session.get(Friendship, request_id)
    if friendship is None or friendship.addressee_id != user.id:
        raise not_found("Friend request")
    if friendship.status is FriendshipStatus.accepted:
        return await _request_out(session, friendship, user.id)
    return await _accept(session, friendship, user.id)


async def _accept(session: SessionDep, f: Friendship, me: uuid.UUID) -> FriendRequestOut:
    f.status = FriendshipStatus.accepted
    f.accepted_at = datetime.now(UTC)
    await session.commit()
    await rooms.publish(f"user:{f.requester_id}", "friend.accepted", {"by": str(me)})
    return await _request_out(session, f, me)


@router.delete("/friends/requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_friend_request(
    request_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Decline (if it was sent to you) or cancel (if you sent it)."""
    friendship = await session.get(Friendship, request_id)
    if (
        friendship is None
        or friendship.status is not FriendshipStatus.pending
        or user.id not in (friendship.requester_id, friendship.addressee_id)
    ):
        raise not_found("Friend request")
    await session.delete(friendship)
    await session.commit()


@router.delete("/friends/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_friend(user_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    friendship = await friendship_between(session, user.id, user_id)
    if friendship is None or friendship.status is not FriendshipStatus.accepted:
        raise not_found("Friend")
    await session.delete(friendship)
    await session.commit()
