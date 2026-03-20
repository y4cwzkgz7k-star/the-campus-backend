"""
WebSocket-based matchmaking router.

Clients connect to /ws/matchmaking/{user_id} and authenticate by
sending an auth message as the very first message:

  {"type": "auth", "token": "<access_token>"}

After successful auth the server replies:

  {"type": "auth_success"}

Then the normal message exchange begins:

  Client → Server:
    {"type": "join",  "payload": {"city": "...", "format": "...", "elo_min": N, "elo_max": N}}
    {"type": "leave"}
    {"type": "ping"}

  Server → Client:
    {"type": "queued",  "payload": {"position": N}}
    {"type": "matched", "payload": {"match_id": "..."}}
    {"type": "expired"}
    {"type": "pong"}
    {"type": "error",   "payload": {"detail": "..."}}
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.database import AsyncSessionLocal
from app.models.user import User

router = APIRouter(tags=["matchmaking"])

# ---------------------------------------------------------------------------
# In-memory queue  {user_id: QueueEntry}
# ---------------------------------------------------------------------------

class QueueEntry:
    def __init__(
        self,
        user_id: str,
        ws: WebSocket,
        city: str,
        format: str,
        elo_min: int,
        elo_max: int,
    ):
        self.user_id = user_id
        self.ws = ws
        self.city = city
        self.format = format
        self.elo_min = elo_min
        self.elo_max = elo_max
        self.joined_at = datetime.now(timezone.utc)


_queue: dict[str, QueueEntry] = {}


async def _send(ws: WebSocket, msg: dict[str, Any]) -> None:
    try:
        await ws.send_text(json.dumps(msg))
    except Exception:
        pass


async def _try_match() -> None:
    """Check queue for compatible pairs and create a match."""
    entries = list(_queue.values())
    for i, a in enumerate(entries):
        for b in entries[i + 1 :]:
            if a.user_id == b.user_id:
                continue
            if a.city != b.city or a.format != b.format:
                continue
            # ELO overlap
            if a.elo_max < b.elo_min or b.elo_max < a.elo_min:
                continue

            match_id = str(uuid.uuid4())
            # Remove both from queue
            _queue.pop(a.user_id, None)
            _queue.pop(b.user_id, None)

            payload = {"match_id": match_id}
            await _send(a.ws, {"type": "matched", "payload": payload})
            await _send(b.ws, {"type": "matched", "payload": payload})
            return


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

AUTH_TIMEOUT_SECONDS = 10


async def _authenticate(
    websocket: WebSocket,
    user_id: str,
) -> bool:
    """Wait for the first message to be an auth message and validate it.

    Returns True on success, False on failure (connection is closed on failure).
    """
    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(),
            timeout=AUTH_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        await _send(websocket, {
            "type": "error",
            "payload": {"detail": "auth timeout — no auth message received"},
        })
        await websocket.close(code=4000)
        return False
    except WebSocketDisconnect:
        return False

    # Parse auth message
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await _send(websocket, {
            "type": "error",
            "payload": {"detail": "invalid JSON in auth message"},
        })
        await websocket.close(code=4000)
        return False

    if msg.get("type") != "auth" or not isinstance(msg.get("token"), str):
        await _send(websocket, {
            "type": "error",
            "payload": {"detail": "first message must be {\"type\": \"auth\", \"token\": \"...\"}"},
        })
        await websocket.close(code=4000)
        return False

    token = msg["token"]

    # Verify JWT
    payload = decode_token(token)
    if not payload or payload.get("type") != "access" or str(payload.get("sub")) != user_id:
        await _send(websocket, {
            "type": "error",
            "payload": {"detail": "invalid or mismatched token"},
        })
        await websocket.close(code=4001)
        return False

    # Verify user exists
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            await _send(websocket, {
                "type": "error",
                "payload": {"detail": "user not found or inactive"},
            })
            await websocket.close(code=4003)
            return False

    await _send(websocket, {"type": "auth_success"})
    return True


@router.websocket("/ws/matchmaking/{user_id}")
async def matchmaking_ws(
    websocket: WebSocket,
    user_id: str,
):
    await websocket.accept()

    # Wait for auth message as the first message
    if not await _authenticate(websocket, user_id):
        return

    try:
        while True:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=60)
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _send(websocket, {"type": "error", "payload": {"detail": "invalid JSON"}})
                continue

            msg_type = msg.get("type")

            if msg_type == "ping":
                await _send(websocket, {"type": "pong"})

            elif msg_type == "join":
                p = msg.get("payload", {})
                entry = QueueEntry(
                    user_id=user_id,
                    ws=websocket,
                    city=p.get("city", ""),
                    format=p.get("format", "1v1"),
                    elo_min=int(p.get("elo_min", 0)),
                    elo_max=int(p.get("elo_max", 9999)),
                )
                _queue[user_id] = entry
                position = len(_queue)
                await _send(websocket, {"type": "queued", "payload": {"position": position}})
                await _try_match()

            elif msg_type == "leave":
                _queue.pop(user_id, None)

            else:
                await _send(websocket, {"type": "error", "payload": {"detail": "unknown message type"}})

    except asyncio.TimeoutError:
        # Send ping to keep alive; if client doesn't respond, drop it
        await _send(websocket, {"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        _queue.pop(user_id, None)
