import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.auth.deps import CurrentUser
from app.core.db import SessionDep
from app.core.errors import api_error, not_found
from app.core.redis import RedisDep
from app.delegation.models import Delegation, Device
from app.delegation.schemas import (
    COMMAND_PERMISSION,
    CommandIn,
    ControllableDeviceOut,
    DelegationIn,
    DelegationOut,
    DeviceIn,
    DeviceOut,
    DeviceRename,
    DeviceState,
)
from app.delegation.service import authorize_device, owned_device
from app.music.router import ProviderDep
from app.playlists.service import load_playlist
from app.realtime.rooms import rooms
from app.users.models import User
from app.users.schemas import UserSummary
from app.users.service import are_friends

router = APIRouter(prefix="/devices", tags=["control delegation"])

STATE_TTL_SECONDS = 86_400


def _device_out(d: Device) -> DeviceOut:
    return DeviceOut(
        id=d.id,
        name=d.name,
        platform=d.platform,
        created_at=d.created_at,
        last_seen_at=d.last_seen_at,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def register_device(body: DeviceIn, user: CurrentUser, session: SessionDep) -> DeviceOut:
    """Called once per app install; the app keeps the returned id."""
    device = Device(owner_id=user.id, name=body.name, platform=body.platform)
    session.add(device)
    await session.commit()
    return _device_out(device)


@router.get("")
async def my_devices(user: CurrentUser, session: SessionDep) -> list[DeviceOut]:
    devices = await session.scalars(
        select(Device).where(Device.owner_id == user.id).order_by(Device.created_at)
    )
    return [_device_out(d) for d in devices]


@router.get("/controllable")
async def controllable_devices(
    user: CurrentUser, session: SessionDep
) -> list[ControllableDeviceOut]:
    """Friends' devices the caller currently holds a valid delegation for."""
    now = datetime.now(UTC)
    rows = await session.execute(
        select(Delegation, Device, User)
        .join(Device, Device.id == Delegation.device_id)
        .join(User, User.id == Device.owner_id)
        .where(
            Delegation.grantee_id == user.id,
            Delegation.revoked_at.is_(None),
            or_(Delegation.expires_at.is_(None), Delegation.expires_at > now),
        )
    )
    out = []
    for delegation, device, owner in rows:
        if await are_friends(session, owner.id, user.id):
            out.append(
                ControllableDeviceOut(
                    **_device_out(device).model_dump(),
                    owner=UserSummary.model_validate(owner),
                    permissions=delegation.permissions,
                    expires_at=delegation.expires_at,
                )
            )
    return out


@router.patch("/{device_id}")
async def rename_device(
    device_id: uuid.UUID, body: DeviceRename, user: CurrentUser, session: SessionDep
) -> DeviceOut:
    device = await owned_device(session, device_id, user.id)
    device.name = body.name
    await session.commit()
    return _device_out(device)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(device_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    device = await owned_device(session, device_id, user.id)
    await session.delete(device)
    await session.commit()
    await rooms.publish(f"device:{device_id}", "device.deleted", {"device_id": str(device_id)})


# --- Delegations (licenses, per device) ----------------------------------------


async def _delegation_out(session: SessionDep, d: Delegation) -> DelegationOut:
    grantee = await session.get(User, d.grantee_id)
    return DelegationOut(
        id=d.id,
        device_id=d.device_id,
        grantee=UserSummary.model_validate(grantee),
        permissions=d.permissions,
        expires_at=d.expires_at,
        created_at=d.created_at,
    )


@router.get("/{device_id}/delegations")
async def list_delegations(
    device_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[DelegationOut]:
    await owned_device(session, device_id, user.id)
    rows = await session.scalars(
        select(Delegation).where(Delegation.device_id == device_id, Delegation.revoked_at.is_(None))
    )
    return [await _delegation_out(session, d) for d in rows]


@router.post("/{device_id}/delegations", status_code=status.HTTP_201_CREATED)
async def grant(
    device_id: uuid.UUID, body: DelegationIn, user: CurrentUser, session: SessionDep
) -> DelegationOut:
    await owned_device(session, device_id, user.id)
    if not await are_friends(session, user.id, body.grantee_id):
        raise api_error(400, "not_friends", "You can only delegate control to a friend")
    if body.expires_at is not None and body.expires_at <= datetime.now(UTC):
        raise api_error(400, "invalid_expiry", "expires_at must be in the future")
    delegation = Delegation(
        device_id=device_id,
        grantee_id=body.grantee_id,
        permissions=sorted(set(body.permissions)),
        expires_at=body.expires_at,
    )
    session.add(delegation)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise api_error(409, "already_delegated", "Revoke the current delegation first") from None
    await rooms.publish(
        f"user:{body.grantee_id}", "delegation.granted", {"device_id": str(device_id)}
    )
    return await _delegation_out(session, delegation)


@router.delete("/{device_id}/delegations/{delegation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke(
    device_id: uuid.UUID, delegation_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    await owned_device(session, device_id, user.id)
    delegation = await session.get(Delegation, delegation_id)
    if delegation is None or delegation.device_id != device_id or delegation.revoked_at:
        raise not_found("Delegation")
    delegation.revoked_at = datetime.now(UTC)
    await session.commit()
    # Effective at once: commands are re-checked on every call, and the friend's
    # sockets leave the device room on every worker.
    await rooms.kick(f"device:{device_id}", delegation.grantee_id)
    await rooms.publish(
        f"user:{delegation.grantee_id}", "delegation.revoked", {"device_id": str(device_id)}
    )


# --- Commands and state ----------------------------------------------------------


@router.post("/{device_id}/commands", status_code=status.HTTP_202_ACCEPTED)
async def send_command(
    device_id: uuid.UUID,
    body: CommandIn,
    user: CurrentUser,
    session: SessionDep,
    provider: ProviderDep,
) -> dict[str, int]:
    """Checked against the license, then pushed to the device through its room.
    202: the device applies it and reports its new state."""
    await authorize_device(session, device_id, user.id, COMMAND_PERMISSION[body.command])
    payload: dict = {"command": body.command, "issued_by": str(user.id)}
    if body.command == "play_track":
        assert body.track is not None
        payload["track"] = (await provider.get_track(body.track.external_id)).model_dump()
    elif body.command == "play_playlist":
        assert body.playlist_id is not None
        await load_playlist(session, body.playlist_id, user.id)  # the issuer must see it
        payload["playlist_id"] = str(body.playlist_id)
    elif body.command == "set_volume":
        payload["volume"] = body.volume
    seq = await rooms.publish(f"device:{device_id}", "device.command", payload)
    return {"seq": seq}


@router.put("/{device_id}/state", status_code=status.HTTP_204_NO_CONTENT)
async def report_state(
    device_id: uuid.UUID, body: DeviceState, user: CurrentUser, session: SessionDep, redis: RedisDep
) -> None:
    """Only the owner's device reports. State is ephemeral: Redis, not Postgres."""
    device = await owned_device(session, device_id, user.id)
    device.last_seen_at = datetime.now(UTC)
    await session.commit()
    state = body.model_dump(mode="json")
    await redis.set(f"device:{device_id}:state", json.dumps(state), ex=STATE_TTL_SECONDS)
    await rooms.publish(f"device:{device_id}", "device.state", state)


@router.get("/{device_id}/state")
async def get_state(
    device_id: uuid.UUID, user: CurrentUser, session: SessionDep, redis: RedisDep
) -> DeviceState | None:
    await authorize_device(session, device_id, user.id, None)
    raw = await redis.get(f"device:{device_id}:state")
    return DeviceState.model_validate_json(raw) if raw else None
