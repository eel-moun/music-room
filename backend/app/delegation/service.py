import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import forbidden, not_found
from app.delegation.models import Delegation, Device
from app.policies.access import can_control_device
from app.users.service import are_friends


async def active_delegation(
    session: AsyncSession, device_id: uuid.UUID, user_id: uuid.UUID
) -> Delegation | None:
    return await session.scalar(
        select(Delegation).where(
            Delegation.device_id == device_id,
            Delegation.grantee_id == user_id,
            Delegation.revoked_at.is_(None),
        )
    )


async def authorize_device(
    session: AsyncSession, device_id: uuid.UUID, user_id: uuid.UUID, permission: str | None
) -> Device:
    """Owner, or a friend holding a valid delegation with `permission` (None: watch only)."""
    device = await session.get(Device, device_id)
    if device is None:
        raise not_found("Device")
    is_owner = device.owner_id == user_id
    delegation = None if is_owner else await active_delegation(session, device_id, user_id)
    decision = can_control_device(
        is_owner=is_owner,
        delegation=delegation,
        are_friends=not is_owner
        and delegation is not None
        and await are_friends(session, device.owner_id, user_id),
        permission=permission,
        now=datetime.now(UTC),
    )
    if not decision.allowed:
        if decision.code == "not_found":
            raise not_found("Device")
        raise forbidden(decision.code, decision.message)
    return device


async def owned_device(session: AsyncSession, device_id: uuid.UUID, user_id: uuid.UUID) -> Device:
    device = await session.get(Device, device_id)
    if device is None or device.owner_id != user_id:
        raise not_found("Device")
    return device
