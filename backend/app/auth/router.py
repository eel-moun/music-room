from collections.abc import Callable
from html import escape
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import service
from app.auth.deps import CurrentUser
from app.auth.google import GoogleIdentity, get_google_verifier
from app.auth.models import EmailTokenPurpose
from app.auth.schemas import (
    ChangePasswordIn,
    EmailIn,
    GoogleIn,
    LoginIn,
    Message,
    RefreshIn,
    RegisterIn,
    ResetPasswordIn,
    TokenIn,
    TokenPair,
)
from app.core.config import get_settings
from app.core.db import SessionDep
from app.core.email import send_email
from app.core.errors import api_error
from app.core.ratelimit import enforce
from app.core.redis import RedisDep
from app.core.security import hash_password, verify_password
from app.users.models import AuthIdentity, User

router = APIRouter(prefix="/auth", tags=["auth"])
# Routes opened from an email link in a browser: no app, so no device headers.
public_router = APIRouter(prefix="/auth", tags=["auth"])

GoogleVerifier = Annotated[Callable, Depends(get_google_verifier)]
CHECK_INBOX = Message(message="If the address can receive email, a message is on its way")


def client_ip(request: Request) -> str:
    # Direct connection only. Behind a reverse proxy, read X-Forwarded-For from that proxy.
    return request.client.host if request.client else "unknown"


async def _user_by_email(session: SessionDep, email: str) -> User | None:
    return await session.scalar(select(User).where(User.email == email.lower()))


async def _send_verification(session: SessionDep, tasks: BackgroundTasks, user: User) -> None:
    token = await service.create_email_token(session, user.id, EmailTokenPurpose.verify_email)
    link = f"{get_settings().public_base_url}/auth/verify-email?token={token}"
    tasks.add_task(
        send_email,
        user.email,
        "Verify your Music Room email",
        f"Hi {user.display_name},\n\nOpen this link to verify your email:\n{link}\n\n"
        "If you didn't create an account, ignore this message.",
    )


@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
async def register(
    body: RegisterIn, request: Request, session: SessionDep, redis: RedisDep, tasks: BackgroundTasks
) -> Message:
    """Always answers the same way, so this endpoint can't be used to test which
    emails have an account. An existing user gets an email instead."""
    await enforce(redis, f"register:ip:{client_ip(request)}", limit=10, window_seconds=3600)
    email = body.email.lower()
    existing = await _user_by_email(session, email)
    if existing is not None:
        tasks.add_task(
            send_email,
            email,
            "Music Room sign-up attempt",
            "Someone tried to create an account with this email. You already have one: "
            "log in, or use 'Forgot password' in the app.",
        )
        return CHECK_INBOX

    user = User(
        email=email,
        password_hash=await hash_password(body.password),
        display_name=body.display_name,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:  # same email registered concurrently
        await session.rollback()
        return CHECK_INBOX
    await _send_verification(session, tasks, user)
    return CHECK_INBOX


@router.post("/verify-email")
async def verify_email(body: TokenIn, session: SessionDep) -> Message:
    if not await _mark_verified(session, body.token):
        raise api_error(400, "invalid_token", "This link is invalid or has expired")
    return Message(message="Email verified, you can log in")


@public_router.get("/verify-email", response_class=HTMLResponse, include_in_schema=False)
async def verify_email_link(token: str, session: SessionDep) -> HTMLResponse:
    ok = await _mark_verified(session, token[:100])
    text = (
        "Email verified. You can go back to the app and log in."
        if ok
        else ("This link is invalid or has expired. Ask the app for a new one.")
    )
    return HTMLResponse(
        f"<!doctype html><meta name=viewport content='width=device-width'>"
        f"<title>Music Room</title><p style='font:18px sans-serif;margin:2em'>{escape(text)}</p>",
        status_code=200 if ok else 400,
    )


async def _mark_verified(session: SessionDep, token: str) -> bool:
    user_id = await service.consume_email_token(session, token, EmailTokenPurpose.verify_email)
    user = await session.get(User, user_id) if user_id else None
    if user is None:
        return False
    user.email_verified = True
    await session.commit()
    return True


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    body: EmailIn, request: Request, session: SessionDep, redis: RedisDep, tasks: BackgroundTasks
) -> Message:
    await enforce(redis, f"resend:ip:{client_ip(request)}", limit=10, window_seconds=3600)
    await enforce(redis, f"resend:acct:{body.email.lower()}", limit=3, window_seconds=3600)
    user = await _user_by_email(session, body.email)
    if user is not None and not user.email_verified:
        await _send_verification(session, tasks, user)
    return CHECK_INBOX


@router.post("/login")
async def login(body: LoginIn, request: Request, session: SessionDep, redis: RedisDep) -> TokenPair:
    # Per IP stops one machine trying many accounts; per account stops many
    # machines (a botnet) guessing one password.
    await enforce(redis, f"login:ip:{client_ip(request)}", limit=30, window_seconds=300)
    await enforce(redis, f"login:acct:{body.email.lower()}", limit=10, window_seconds=900)
    user = await _user_by_email(session, body.email)
    # Always run argon2 (on a dummy hash if needed): same timing for unknown emails.
    if not await verify_password(body.password, user.password_hash if user else None):
        raise api_error(401, "invalid_credentials", "Wrong email or password")
    assert user is not None
    if not user.email_verified:
        raise api_error(403, "email_not_verified", "Verify your email before logging in")
    return await service.issue_tokens(session, user.id)


@router.post("/refresh")
async def refresh(
    body: RefreshIn, request: Request, session: SessionDep, redis: RedisDep
) -> TokenPair:
    await enforce(redis, f"refresh:ip:{client_ip(request)}", limit=60, window_seconds=60)
    try:
        return await service.rotate_refresh_token(session, body.refresh_token)
    except service.InvalidRefreshToken:
        raise api_error(401, "invalid_refresh_token", "Session expired, log in again") from None


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshIn, session: SessionDep) -> None:
    await service.logout(session, body.refresh_token)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    body: EmailIn, request: Request, session: SessionDep, redis: RedisDep, tasks: BackgroundTasks
) -> Message:
    await enforce(redis, f"forgot:ip:{client_ip(request)}", limit=10, window_seconds=3600)
    await enforce(redis, f"forgot:acct:{body.email.lower()}", limit=3, window_seconds=3600)
    user = await _user_by_email(session, body.email)
    if user is not None:
        token = await service.create_email_token(session, user.id, EmailTokenPurpose.reset_password)
        tasks.add_task(
            send_email,
            user.email,
            "Reset your Music Room password",
            f"Hi {user.display_name},\n\nIn the app, open 'Reset password' and paste this code:\n\n"
            f"{token}\n\nIt expires in 24 hours. If you didn't ask for this, ignore this message.",
        )
    return CHECK_INBOX


@router.post("/reset-password")
async def reset_password(body: ResetPasswordIn, session: SessionDep) -> Message:
    user_id = await service.consume_email_token(
        session, body.token, EmailTokenPurpose.reset_password
    )
    user = await session.get(User, user_id) if user_id else None
    if user is None:
        raise api_error(400, "invalid_token", "This code is invalid or has expired")
    user.password_hash = await hash_password(body.new_password)
    user.email_verified = True  # they just proved they read this inbox
    await session.commit()
    # A reset usually means the password leaked: end every existing session.
    await service.revoke_all_for_user(session, user.id)
    return Message(message="Password changed, you can log in")


@router.post("/change-password")
async def change_password(
    body: ChangePasswordIn, user: CurrentUser, session: SessionDep
) -> Message:
    if user.password_hash is not None and not await verify_password(
        body.current_password or "", user.password_hash
    ):
        raise api_error(401, "invalid_credentials", "Current password is wrong")
    user.password_hash = await hash_password(body.new_password)
    await session.commit()
    return Message(message="Password changed")


@router.post("/google")
async def google_login(
    body: GoogleIn, request: Request, session: SessionDep, redis: RedisDep, verify: GoogleVerifier
) -> TokenPair:
    """Log in with Google, or sign up if this Google account and its email are new."""
    await enforce(redis, f"google:ip:{client_ip(request)}", limit=30, window_seconds=300)
    google: GoogleIdentity = await verify(body.id_token)

    identity = await session.scalar(
        select(AuthIdentity).where(
            AuthIdentity.provider == "google", AuthIdentity.subject == google.subject
        )
    )
    if identity is not None:
        return await service.issue_tokens(session, identity.user_id)

    if await _user_by_email(session, google.email) is not None:
        # No silent merge: the existing owner must log in and link Google themselves.
        # Otherwise whoever controls a Google account with that email takes the account.
        raise api_error(
            409,
            "account_exists",
            "An account already uses this email. Log in with your password, "
            "then link Google from your profile.",
        )

    user = User(
        email=google.email,
        password_hash=None,
        email_verified=google.email_verified,
        display_name=(google.name or google.email.split("@")[0])[:50],
    )
    session.add(user)
    await session.flush()
    session.add(
        AuthIdentity(user_id=user.id, provider="google", subject=google.subject, email=google.email)
    )
    try:
        await session.commit()
    except IntegrityError:  # same Google account signing up twice at once
        await session.rollback()
        raise api_error(409, "account_exists", "Try again") from None
    return await service.issue_tokens(session, user.id)


@router.post("/google/link")
async def link_google(
    body: GoogleIn, user: CurrentUser, session: SessionDep, verify: GoogleVerifier
) -> Message:
    google: GoogleIdentity = await verify(body.id_token)
    owner_id = await session.scalar(
        select(AuthIdentity.user_id).where(
            AuthIdentity.provider == "google", AuthIdentity.subject == google.subject
        )
    )
    if owner_id == user.id:
        return Message(message="Google account already linked")
    if owner_id is not None:
        raise api_error(
            409, "google_linked_elsewhere", "This Google account is used by another user"
        )
    session.add(
        AuthIdentity(user_id=user.id, provider="google", subject=google.subject, email=google.email)
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise api_error(
            409, "google_already_linked", "Unlink your current Google account first"
        ) from None
    return Message(message="Google account linked")


@router.delete("/google/link")
async def unlink_google(user: CurrentUser, session: SessionDep) -> Message:
    identity = await session.scalar(
        select(AuthIdentity).where(
            AuthIdentity.user_id == user.id, AuthIdentity.provider == "google"
        )
    )
    if identity is None:
        raise api_error(404, "not_found", "No Google account linked")
    if user.password_hash is None:
        raise api_error(409, "last_login_method", "Set a password before unlinking Google")
    await session.delete(identity)
    await session.commit()
    return Message(message="Google account unlinked")
