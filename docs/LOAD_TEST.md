# Load test

How many people can use Music Room at the same time, on what hardware, and what breaks first.

> Measured on 2026-10-29 with k6 1.8.2. Raw k6 summaries are in `loadtest/results/` (gitignored, regenerate with the commands below).

## Server

| | |
|---|---|
| Machine | On premise, one desktop PC (no cloud) |
| CPU | Intel Core i7-14700: 20 cores / 28 threads, up to 5.4 GHz |
| RAM | 16 GB (the API container is capped at 1 GB, Postgres 1 GB, Redis 256 MB) |
| OS | Linux 6.8, Docker 29.3 (rootless), cgroup v2 |
| Stack | `docker-compose.prod.yml`: FastAPI on uvicorn (2 workers by default), PostgreSQL 18.6, Redis 8.8 |
| Load generator | k6 in a container **on the same machine** (it used ~1.4 CPU at peak, so the API had slightly less than a dedicated server would) |

CPU limits can't be set on this host (the kernel has no CFS cgroup controller), so the API process uses as many cores as it has workers.

## Scenarios

`loadtest/mixed.js` models real users of the **3 services at once**, with think times:

| Share of users | Does | Think time |
|---|---|---|
| 55 % voters (Track Vote) | read the queue, vote or withdraw a vote | 1–3 s |
| 25 % editors (Playlist Editor) | read the playlist, move a track with the expected version | 2–5 s |
| 10 % controllers (Control Delegation) | send play / pause / volume to a delegated device | 2–5 s |
| 10 % listeners (realtime) | keep a WebSocket open on the event, receive every queue update | 30 s sessions |

All users act on the same event, playlist and device: the worst case for contention (one hot row, every update fanned out to every listener).

`loadtest/stress.js` removes think times and raises the request rate every minute until p95 latency passes 2 s (the test then aborts itself).

Pass criteria for "the service holds": **p95 < 500 ms, p99 < 1 s, < 1 % errors**.

## Results

### Simultaneous users (mixed.js, 90 s at full load after a 30 s ramp)

| Workers | Users | Requests/s | Median | p95 | Errors | WS messages/s | Verdict |
|---|---|---|---|---|---|---|---|
| 2 (default) | **800** | 440 | 32 ms | **132 ms** | 0 % | 5 471 | ✅ holds |
| 2 | 1 000 | 494 | 85 ms | 672 ms | 0 % | 7 192 | ❌ too slow |
| 2 | 1 200 | 491 | 94 ms | 1 834 ms | 0 % | 8 161 | ❌ |
| 8 | 1 800 | 883 | 88 ms | 672 ms | 0 % | 20 567 | ❌ too slow |
| 8 | 2 500 | 1 044 | 213 ms | 1 464 ms | 0 % | 19 448 | ❌ |

### Breaking point (stress.js)

| Workers | Peak sustained throughput | CPU at saturation |
|---|---|---|
| 2 | ~600 requests/s | API 200–215 % (2 cores full), Postgres 66–86 % |
| 8 | ~1 540 requests/s | API 807 % (8 cores full), Postgres 340 % |

Peak throughput is read from Prometheus (`max_over_time(sum(rate(http_requests_total[30s]))[20m:5s])`).

**No request failed in any run.** Past saturation, requests queue up and latency grows, but nothing crashes, no vote is lost and no connection is refused.

## Conclusion

**On this machine, with the default configuration (2 workers), Music Room serves about 800 simultaneous active users across the 3 services with p95 latency under 150 ms.** The limit is between 800 and 1 000 users. With 8 workers the limit is higher, but below 1 800 users (already over the latency target). About 1 400 is an **estimate** from the throughput ratio; that point wasn't measured.

That is consistent with the platform: a single desktop-class server handles hundreds to low thousands of users. A Raspberry Pi would handle dozens.

## Bottleneck analysis

1. **API CPU (Python), first.** In every run the API container is pinned at 100 % × the number of workers, while Postgres still has headroom and Redis stays under 2 %. Each uvicorn worker is one Python process on one core. 4× the workers gave about 2.5× the throughput: not linear, because Postgres starts to take a real share of the CPU (it shares the same machine) and k6 competes for cores too.
2. **The cost of a vote.** A vote is cheap to store (one `INSERT … ON CONFLICT DO NOTHING`), but each one then:
   - recomputes the full ranking (GROUP BY + COUNT) twice: once for the broadcast and once for the HTTP response;
   - serializes the whole queue to JSON;
   - publishes it to every listener. At 800 users that is ~5 500 WebSocket messages/s; at 1 800 users ~20 000/s.
3. **The hot playlist row.** With every editor moving tracks in one playlist, ~6 % of moves get a `409` (the optimistic lock doing its job). Those requests are cheap, but the users have to retry.

## What would raise the limit

| Change | Expected effect | Cost |
|---|---|---|
| More workers or more servers behind a load balancer (the realtime layer already works across processes through Redis) | Roughly linear until Postgres saturates | Infrastructure |
| Coalesce `queue.updated`: publish at most every ~200 ms per event instead of once per vote | Removes most of the ranking queries and WebSocket traffic at peak | A small delay before updates show up |
| Keep the ranking in a Redis sorted set (`ZINCRBY`) next to Postgres | Ranking read becomes O(log n) instead of GROUP BY | Two sources to keep consistent |
| Return the vote response without recomputing the ranking (the broadcast already carries it) | Halves the ranking queries | The app relies on the push |
| Postgres on its own machine, with PgBouncer | Removes CPU contention with the API | Infrastructure |

## Reproduce

```bash
make obs-up                                       # prod stack + Grafana on http://localhost:3000
make loadtest-tokens n=500                        # 500 users + access tokens (valid 15 min)
make loadtest s=mixed args="-e VUS=800 -e DURATION=90s"
make loadtest s=stress args="-e PEAK=3000"
WEB_WORKERS=8 DB_POOL_SIZE=5 DB_MAX_OVERFLOW=5 make prod-up   # 8 workers, 80 DB connections max
```

Watch the "Music Room API" dashboard during the run: requests/s, p50/p95/p99, errors, open sockets and realtime events per second.

Logins aren't part of the load. All k6 traffic comes from one IP, and the login rate limit (30 per 5 min per IP, see SECURITY.md) would block it, which is the protection working as intended. Tokens are issued directly by `scripts/seed.py --tokens` instead. An argon2 verification costs **~40 ms** of CPU here (argon2id, t=3, 64 MiB, p=4, measured). That caps one worker at ~25 logins/s, so a login is the most expensive request per call. It runs in a thread pool, so it doesn't block the other requests on that worker.
