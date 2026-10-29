"""Create verified test users (for load tests and manual checks).

docker compose exec api python -m scripts.seed --users 200
→ loadtest0@example.com ... loadtest199@example.com, password "loadtest-password"
"""

import argparse
import asyncio
import json
import sys

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

import app.models  # noqa: F401
from app.core.db import SessionLocal, engine
from app.core.security import create_access_token, hash_password
from app.users.models import User

PASSWORD = "loadtest-password"


async def seed(count: int, tokens: bool) -> None:
    password_hash = await hash_password(PASSWORD)  # one argon2 hash, shared: seeding stays fast
    rows = [
        {
            "email": f"loadtest{i}@example.com",
            "password_hash": password_hash,
            "email_verified": True,
            "display_name": f"Load tester {i}",
            "public_info": {},
            "friends_info": {},
            "private_info": {},
            "music_preferences": {},
        }
        for i in range(count)
    ]
    async with SessionLocal() as session:
        result = await session.execute(insert(User).values(rows).on_conflict_do_nothing())
        await session.commit()
        emails = [r["email"] for r in rows]
        users = await session.scalars(select(User).where(User.email.in_(emails)))
        issued = [{"id": str(u.id), "token": create_access_token(u.id)} for u in users]
    await engine.dispose()
    if tokens:
        json.dump(issued, sys.stdout)
    else:
        print(f"{result.rowcount} new users (of {count}); password: {PASSWORD}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=200)
    parser.add_argument("--tokens", action="store_true", help="print access tokens as JSON")
    args = parser.parse_args()
    asyncio.run(seed(args.users, args.tokens))
