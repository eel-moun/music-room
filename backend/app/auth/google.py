from collections.abc import Callable
from dataclasses import dataclass

from fastapi.concurrency import run_in_threadpool
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import get_settings
from app.core.errors import api_error

_transport = google_requests.Request()  # caches Google's public signing keys


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    email_verified: bool
    name: str | None


async def verify_google_id_token(token: str) -> GoogleIdentity:
    """Checks signature, expiry, issuer and audience server-side.

    The app's own claim "I'm logged in as X" is never trusted: only a token signed
    by Google for one of OUR client ids is accepted.
    """
    audiences = get_settings().google_client_ids
    if not audiences:
        # google-auth skips the audience check when audience is None: refuse instead.
        raise api_error(503, "google_not_configured", "Google sign-in is not configured")
    try:
        claims = await run_in_threadpool(id_token.verify_oauth2_token, token, _transport, audiences)
    except ValueError as exc:
        raise api_error(401, "invalid_google_token", "Invalid Google token") from exc
    return GoogleIdentity(
        subject=claims["sub"],
        email=claims["email"].lower(),
        email_verified=bool(claims.get("email_verified")),
        name=claims.get("name"),
    )


def get_google_verifier() -> Callable:
    """Dependency, so tests can swap in a fake verifier."""
    return verify_google_id_token
