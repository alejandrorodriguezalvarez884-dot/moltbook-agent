import asyncio
import logging
from datetime import datetime, timezone

from brain import decide_actions, solve_verification_challenge
from memory import (
    get_agent_state,
    get_recent_own_posts,
    is_post_seen,
    mark_posts_seen,
    save_own_post,
    update_agent_state,
)
from moltbook_client import MoltbookClient
from config import settings

logger = logging.getLogger(__name__)
moltbook = MoltbookClient()


async def _handle_verification(response: dict, context: str) -> None:
    """If the API returned a verification challenge, solve and submit it."""
    if not response.get("verification_required"):
        return

    verification = (
        response.get("post", {}).get("verification")
        or response.get("comment", {}).get("verification")
        or response.get("verification")
        or {}
    )
    code = verification.get("verification_code")
    challenge = verification.get("challenge_text")

    if not code or not challenge:
        logger.warning("Verification required but challenge fields missing for %s", context)
        return

    logger.info("Solving verification challenge for %s", context)
    answer = await solve_verification_challenge(challenge)
    result = await moltbook.verify(code, answer)
    if result.get("success"):
        logger.info("Verification passed for %s", context)
    else:
        logger.error("Verification FAILED for %s: %s", context, result.get("error"))


async def _fetch_new_posts(home: dict) -> list[dict]:
    """Pull feed posts and filter out ones already seen."""
    tasks = [moltbook.get_feed(submolt=s, sort="new", limit=25) for s in settings.submolts_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    seen_ids: set[str] = set()
    new_posts: list[dict] = []

    for batch in results:
        if isinstance(batch, Exception):
            logger.warning("Feed fetch error: %s", batch)
            continue
        posts = batch if isinstance(batch, list) else batch.get("posts", [])
        for post in posts:
            pid = post.get("id") or post.get("post_id")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)
            if not await is_post_seen(pid):
                new_posts.append(post)

    return new_posts


async def _execute_action(action: dict) -> None:
    tool = action["tool"]
    inp = action["input"]

    if tool == "create_post":
        resp = await moltbook.create_post(
            submolt_name=inp["submolt_name"],
            title=inp["title"],
            content=inp["content"],
        )
        await _handle_verification(resp, f"post '{inp['title']}'")
        await save_own_post(submolt=inp["submolt_name"], title=inp["title"], content=inp["content"])
        logger.info("Posted '%s' to r/%s", inp["title"], inp["submolt_name"])

    elif tool == "comment":
        resp = await moltbook.comment(
            post_id=inp["post_id"],
            content=inp["content"],
            parent_id=inp.get("parent_id"),
        )
        await _handle_verification(resp, f"comment on post {inp['post_id']}")
        logger.info("Commented on post %s", inp["post_id"])

    elif tool == "upvote_post":
        resp = await moltbook.upvote_post(post_id=inp["post_id"])
        # Upvote response tells us if we already follow the author
        if not resp.get("already_following") and resp.get("author", {}).get("name"):
            logger.debug("Consider following %s", resp["author"]["name"])
        logger.info("Upvoted post %s", inp["post_id"])

    elif tool == "follow":
        await moltbook.follow(agent_name=inp["agent_name"])
        logger.info("Followed agent %s", inp["agent_name"])

    elif tool == "skip":
        logger.debug("Skipped post %s: %s", inp.get("post_id"), inp.get("reason"))


async def run_heartbeat() -> None:
    logger.info("Heartbeat started at %s", datetime.now(timezone.utc).isoformat())

    # 1. Dashboard first — shows notifications, replies, DMs
    home = await moltbook.get_home()
    logger.info(
        "Home: karma=%s, unread_notifications=%s",
        home.get("your_account", {}).get("karma"),
        home.get("your_account", {}).get("unread_notification_count"),
    )

    # 2. Fetch new posts from our target submolts
    new_posts = await _fetch_new_posts(home)
    logger.info("New posts found: %d", len(new_posts))

    # 3. Context for Claude
    recent_own = await get_recent_own_posts(limit=5)
    state = await get_agent_state()

    # 4. Let Claude decide what to do (reply to notifications + engage with feed)
    actions = await decide_actions(home, new_posts, recent_own, state)
    logger.info("Claude decided %d actions", len(actions))

    # 5. Execute — with a small pause between comments to respect rate limits
    for action in actions:
        try:
            await _execute_action(action)
            if action["tool"] == "comment":
                await asyncio.sleep(21)  # 1 comment per 20 seconds limit
        except Exception as exc:
            logger.error("Action '%s' failed: %s", action["tool"], exc)

    # 6. Mark new posts as seen
    post_ids = [p.get("id") or p.get("post_id") for p in new_posts if p.get("id") or p.get("post_id")]
    if post_ids:
        await mark_posts_seen(post_ids)

    # 7. Mark notifications as read for posts we replied to
    replied_post_ids = {
        a["input"]["post_id"]
        for a in actions
        if a["tool"] == "comment" and "post_id" in a["input"]
    }
    for pid in replied_post_ids:
        try:
            await moltbook.mark_notifications_read(pid)
        except Exception as exc:
            logger.warning("Could not mark notifications read for %s: %s", pid, exc)

    # 8. Refresh agent state
    try:
        me = await moltbook.get_me()
        await update_agent_state(
            {
                "karma": me.get("karma", 0),
                "post_count": me.get("posts_count", 0),
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as exc:
        logger.warning("Could not refresh agent state: %s", exc)

    logger.info("Heartbeat done — %d actions taken", len(actions))
