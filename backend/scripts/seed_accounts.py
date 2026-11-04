"""Create a few verified accounts with profiles and friendships, for manual testing.

make seed        (dev stack)    make prod-seed   (prod stack)
→ alice, bob, carol, dave, eve @example.com, password "musicroom-test"

Relations, so visibility rules can be checked from each side:
  alice ↔ bob, alice ↔ carol   friends (accepted)
  dave → alice                 pending request (alice sees it as incoming)
  eve                          no relation: a stranger to everyone

Idempotent: existing accounts and friendships are left as they are.
"""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

import app.models  # noqa: F401
from app.core.db import SessionLocal, engine
from app.core.security import hash_password
from app.users.models import Friendship, FriendshipStatus, User

PASSWORD = "musicroom-test"

ACCOUNTS = [
    {
        "name": "alice",
        "display_name": "Alice",
        "public_info": {"bio": "Hosts the Friday listening parties."},
        "friends_info": {"first_name": "Alice", "last_name": "Martin", "city": "Lyon"},
        "private_info": {"phone": "+33 6 00 00 00 01", "birth_date": "1998-04-12"},
        "music_preferences": {"genres": ["house", "jazz"], "favorite_artists": ["Daft Punk"]},
    },
    {
        "name": "bob",
        "display_name": "Bob",
        "public_info": {"bio": "Always votes for drum and bass."},
        "friends_info": {"first_name": "Bob", "last_name": "Durand", "city": "Paris"},
        "private_info": {"phone": "+33 6 00 00 00 02"},
        "music_preferences": {"genres": ["drum and bass", "techno"], "favorite_artists": []},
    },
    {
        "name": "carol",
        "display_name": "Carol",
        "public_info": {"bio": ""},
        "friends_info": {"first_name": "Carol", "city": "Lyon"},
        "private_info": {},
        "music_preferences": {"genres": ["hip hop"], "favorite_artists": ["MF DOOM"]},
    },
    {
        "name": "dave",
        "display_name": "Dave",
        "public_info": {"bio": "New here."},
        "friends_info": {"city": "Marseille"},
        "private_info": {},
        "music_preferences": {"genres": ["rock"], "favorite_artists": []},
    },
    {
        "name": "eve",
        "display_name": "Eve",
        "public_info": {"bio": "Just browsing."},
        "friends_info": {"first_name": "Eve", "city": "Nice"},
        "private_info": {"birth_date": "2000-01-01"},
        "music_preferences": {"genres": ["ambient"], "favorite_artists": []},
    },
]

# (requester, addressee, status)
FRIENDSHIPS = [
    ("alice", "bob", FriendshipStatus.accepted),
    ("carol", "alice", FriendshipStatus.accepted),
    ("dave", "alice", FriendshipStatus.pending),
]


def email(name: str) -> str:
    return f"{name}@example.com"


async def seed() -> None:
    password_hash = await hash_password(PASSWORD)  # one argon2 hash, shared
    users = [
        {
            "email": email(a["name"]),
            "password_hash": password_hash,
            "email_verified": True,
            **{k: v for k, v in a.items() if k != "name"},
        }
        for a in ACCOUNTS
    ]
    async with SessionLocal() as session:
        created = await session.execute(insert(User).values(users).on_conflict_do_nothing())
        rows = await session.execute(
            select(User.email, User.id).where(User.email.in_([u["email"] for u in users]))
        )
        ids = dict(rows.all())
        now = datetime.now(UTC)
        friendships = [
            {
                "requester_id": ids[email(a)],
                "addressee_id": ids[email(b)],
                "status": status,
                "accepted_at": now if status is FriendshipStatus.accepted else None,
            }
            for a, b, status in FRIENDSHIPS
        ]
        # No conflict target: the pair index is on expressions (least/greatest).
        linked = await session.execute(
            insert(Friendship).values(friendships).on_conflict_do_nothing()
        )
        await session.commit()
    await engine.dispose()

    print(f"{created.rowcount} new accounts, {linked.rowcount} new friendships")
    print(f"Password for all: {PASSWORD}")
    for a in ACCOUNTS:
        print(f"  {email(a['name'])}")
    print("alice ↔ bob, alice ↔ carol: friends · dave → alice: pending · eve: stranger")


if __name__ == "__main__":
    asyncio.run(seed())
