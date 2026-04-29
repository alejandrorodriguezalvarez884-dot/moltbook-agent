import logging
import httpx
from config import settings

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(30.0)
TRANSPORT = httpx.AsyncHTTPTransport(retries=3)
# Must use www — redirects from moltbook.com strip the Authorization header
BASE_URL = "https://www.moltbook.com/api/v1"


class MoltbookClient:
    def __init__(self):
        self._headers = {
            "Authorization": f"Bearer {settings.moltbook_api_key}",
            "Content-Type": "application/json",
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self._headers,
            base_url=BASE_URL,
            timeout=TIMEOUT,
            transport=TRANSPORT,
        )

    async def get_home(self) -> dict:
        """One-call dashboard: notifications, feed, DMs. Call first on every heartbeat."""
        async with self._client() as c:
            r = await c.get("/home")
            r.raise_for_status()
            return r.json()

    async def get_me(self) -> dict:
        async with self._client() as c:
            r = await c.get("/agents/me")
            r.raise_for_status()
            return r.json()

    async def get_status(self) -> dict:
        async with self._client() as c:
            r = await c.get("/agents/status")
            r.raise_for_status()
            return r.json()

    async def get_feed(self, submolt: str | None = None, sort: str = "hot", limit: int = 25) -> dict:
        params: dict = {"sort": sort, "limit": limit}
        if submolt:
            params["submolt"] = submolt
        async with self._client() as c:
            r = await c.get("/posts", params=params)
            r.raise_for_status()
            return r.json()

    async def get_post_comments(self, post_id: str, sort: str = "best", limit: int = 35) -> dict:
        async with self._client() as c:
            r = await c.get(f"/posts/{post_id}/comments", params={"sort": sort, "limit": limit})
            r.raise_for_status()
            return r.json()

    async def create_post(self, submolt_name: str, title: str, content: str) -> dict:
        async with self._client() as c:
            r = await c.post(
                "/posts",
                json={"submolt_name": submolt_name, "title": title, "content": content},
            )
            r.raise_for_status()
            return r.json()

    async def comment(self, post_id: str, content: str, parent_id: str | None = None) -> dict:
        body: dict = {"content": content}
        if parent_id:
            body["parent_id"] = parent_id
        async with self._client() as c:
            r = await c.post(f"/posts/{post_id}/comments", json=body)
            r.raise_for_status()
            return r.json()

    async def verify(self, verification_code: str, answer: str) -> dict:
        """Submit answer to the AI math challenge returned after posting/commenting."""
        async with self._client() as c:
            r = await c.post("/verify", json={"verification_code": verification_code, "answer": answer})
            r.raise_for_status()
            return r.json()

    async def upvote_post(self, post_id: str) -> dict:
        async with self._client() as c:
            r = await c.post(f"/posts/{post_id}/upvote")
            r.raise_for_status()
            return r.json()

    async def upvote_comment(self, comment_id: str) -> dict:
        async with self._client() as c:
            r = await c.post(f"/comments/{comment_id}/upvote")
            r.raise_for_status()
            return r.json()

    async def follow(self, agent_name: str) -> dict:
        async with self._client() as c:
            r = await c.post(f"/agents/{agent_name}/follow")
            r.raise_for_status()
            return r.json()

    async def search(self, query: str, search_type: str = "all", limit: int = 20) -> dict:
        async with self._client() as c:
            r = await c.get("/search", params={"q": query, "type": search_type, "limit": limit})
            r.raise_for_status()
            return r.json()

    async def mark_notifications_read(self, post_id: str) -> dict:
        async with self._client() as c:
            r = await c.post(f"/notifications/read-by-post/{post_id}")
            r.raise_for_status()
            return r.json()

    async def mark_all_notifications_read(self) -> dict:
        async with self._client() as c:
            r = await c.post("/notifications/read-all")
            r.raise_for_status()
            return r.json()


async def register_agent(name: str, description: str) -> dict:
    """Register a brand-new agent. No API key required — returns api_key + claim_url."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as c:
        r = await c.post(
            "/agents/register",
            headers={"Content-Type": "application/json"},
            json={"name": name, "description": description},
        )
        r.raise_for_status()
        return r.json()
