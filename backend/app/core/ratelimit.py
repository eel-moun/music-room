"""Fixed-window rate limiting in Redis (see ADR-004).

INCR a counter named after the action, the subject (IP or account) and nothing else;
the first hit sets the TTL, so the counter resets itself at the end of the window.
"""

from redis.asyncio import Redis

from app.core.errors import api_error


async def enforce(redis: Redis, key: str, limit: int, window_seconds: int) -> None:
    redis_key = f"ratelimit:{key}"
    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds, nx=True)  # only the first hit starts the window
        pipe.ttl(redis_key)
        count, _, ttl = await pipe.execute()
    if count > limit:
        error = api_error(429, "rate_limited", "Too many attempts, try again later")
        error.headers = {"Retry-After": str(max(ttl, 1))}
        raise error
