"""End-to-end check of realtime across uvicorn workers, with the real protocol.

Needs seeded users (python -m scripts.seed) and the 2-worker stack (make prod-up):
    uv run python scripts/check_realtime.py --api http://localhost:8000

1. two users log in over REST, one creates an event
2. each opens a WebSocket (auth message, then subscribe to the event room),
   reconnecting until the two sockets sit on different workers
3. a REST vote is sent; both sockets must receive the same queue.updated event
"""

import argparse
import asyncio
import json

import httpx
from websockets.asyncio.client import ClientConnection, connect

HEADERS = {"X-Platform": "script", "X-Device": "check_realtime", "X-App-Version": "1.0.0"}
TRACK = "bVrd2zW"  # a real Audius track (the prod stack calls Audius)


async def open_socket(ws_url: str, token: str, room: str) -> tuple[ClientConnection, int]:
    socket = await connect(f"{ws_url}/ws", additional_headers=HEADERS)
    await socket.send(json.dumps({"type": "auth", "token": token}))
    ready = json.loads(await socket.recv())
    await socket.send(json.dumps({"type": "subscribe", "room": room}))
    subscribed = json.loads(await socket.recv())
    assert subscribed["type"] == "subscribed", subscribed
    return socket, ready["payload"]["worker"]


async def next_event(socket: ClientConnection) -> dict:
    while True:
        message = json.loads(await asyncio.wait_for(socket.recv(), timeout=5))
        if "seq" in message:
            return message


async def main(api: str) -> None:
    ws_url = api.replace("http", "ws", 1)
    async with httpx.AsyncClient(base_url=api, headers=HEADERS, timeout=10) as http:
        tokens = []
        for i in (0, 1):
            r = await http.post(
                "/auth/login",
                json={"email": f"loadtest{i}@example.com", "password": "loadtest-password"},
            )
            r.raise_for_status()
            tokens.append(r.json()["access_token"])
        auth = [{"Authorization": f"Bearer {t}"} for t in tokens]

        event = (
            await http.post("/events", json={"name": "realtime check"}, headers=auth[0])
        ).json()
        room = f"event:{event['id']}"

        host_socket, host_worker = await open_socket(ws_url, tokens[0], room)
        for _ in range(50):
            guest_socket, guest_worker = await open_socket(ws_url, tokens[1], room)
            if guest_worker != host_worker:
                break
            await guest_socket.close()
        else:
            raise SystemExit("All sockets landed on one worker: is the API running 2 workers?")
        print(f"host socket on worker {host_worker}, guest socket on worker {guest_worker}")

        r = await http.post(
            f"/events/{event['id']}/tracks", json={"external_id": TRACK}, headers=auth[1]
        )
        r.raise_for_status()

        host_event, guest_event = await asyncio.gather(
            next_event(host_socket), next_event(guest_socket)
        )
        assert host_event == guest_event, (host_event, guest_event)
        assert host_event["type"] == "queue.updated"
        title = host_event["payload"]["queue"][0]["title"]
        print(f"both sockets got seq {host_event['seq']} queue.updated ({title!r})")

        await http.delete(f"/events/{event['id']}", headers=auth[0])
        await host_socket.close()
        await guest_socket.close()
    print("OK: realtime works across workers")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    asyncio.run(main(parser.parse_args().api))
