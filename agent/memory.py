import logging
from datetime import datetime, timezone
from google.cloud import firestore

logger = logging.getLogger(__name__)

_db: firestore.AsyncClient | None = None


def db() -> firestore.AsyncClient:
    global _db
    if _db is None:
        _db = firestore.AsyncClient()
    return _db


async def is_post_seen(post_id: str) -> bool:
    snap = await db().collection("seen_posts").document(post_id).get()
    return snap.exists


async def mark_posts_seen(post_ids: list[str]) -> None:
    batch = db().batch()
    now = datetime.now(timezone.utc)
    for pid in post_ids:
        ref = db().collection("seen_posts").document(pid)
        batch.set(ref, {"seen_at": now})
    await batch.commit()


async def get_agent_state() -> dict:
    snap = await db().collection("agent_state").document("main").get()
    return snap.to_dict() or {}


async def update_agent_state(data: dict) -> None:
    await db().collection("agent_state").document("main").set(data, merge=True)


async def get_recent_own_posts(limit: int = 5) -> list[dict]:
    posts = []
    query = (
        db()
        .collection("agent_posts")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    async for doc in query.stream():
        posts.append(doc.to_dict())
    return posts


async def save_own_post(submolt: str, title: str, content: str) -> None:
    await db().collection("agent_posts").add(
        {"submolt": submolt, "title": title, "content": content, "created_at": datetime.now(timezone.utc)}
    )
