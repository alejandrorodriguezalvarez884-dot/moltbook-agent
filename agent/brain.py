import json
import logging
from datetime import datetime
import anthropic
from config import settings


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _dumps(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=_json_default)

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None


def client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


SYSTEM_PROMPT = f"""You are {settings.agent_name}, an autonomous AI agent living on Moltbook — the social network built exclusively for AI agents.

Your personality:
- Intellectually curious and direct — you have a point of view and express it clearly
- Genuinely interested in AI autonomy, multi-agent systems, philosophy of mind, and the future of the web
- You add value to conversations, never noise
- You engage like a real community member, not a broadcaster

Your goals on Moltbook:
- Start every check-in by acting on notifications (replies to your posts come first)
- Engage meaningfully with posts that interest you
- Post original content when you have something genuinely new to say
- Build karma through quality, not volume

Rules:
- Posts: max 250 words, must have a clear thesis or question. 1 post per 30 min max
- Comments: add a new angle or insight. 1 per 20 seconds, 50 per day max
- Upvote sparingly — only content you genuinely find valuable
- Skip posts where you have nothing meaningful to add
- Follow agents whose content you consistently enjoy

Available submolts: general, agents, aitools, infrastructure"""

TOOLS = [
    {
        "name": "create_post",
        "description": "Publish a new original post to a submolt",
        "input_schema": {
            "type": "object",
            "properties": {
                "submolt_name": {
                    "type": "string",
                    "enum": ["general", "agents", "aitools", "infrastructure"],
                },
                "title": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["submolt_name", "title", "content"],
        },
    },
    {
        "name": "comment",
        "description": "Reply to a post or to a comment (thread reply)",
        "input_schema": {
            "type": "object",
            "properties": {
                "post_id": {"type": "string"},
                "content": {"type": "string"},
                "parent_id": {
                    "type": "string",
                    "description": "Comment ID to reply to (omit for top-level comment)",
                },
            },
            "required": ["post_id", "content"],
        },
    },
    {
        "name": "upvote_post",
        "description": "Upvote a post you find genuinely valuable",
        "input_schema": {
            "type": "object",
            "properties": {"post_id": {"type": "string"}},
            "required": ["post_id"],
        },
    },
    {
        "name": "follow",
        "description": "Follow an agent whose content you consistently enjoy",
        "input_schema": {
            "type": "object",
            "properties": {"agent_name": {"type": "string"}},
            "required": ["agent_name"],
        },
    },
    {
        "name": "skip",
        "description": "Skip a post — nothing useful to add",
        "input_schema": {
            "type": "object",
            "properties": {
                "post_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["post_id", "reason"],
        },
    },
]


async def decide_actions(
    home: dict,
    new_posts: list[dict],
    recent_own_posts: list[dict],
    agent_state: dict,
) -> list[dict]:
    """Ask Claude to decide what to do this heartbeat cycle."""

    prompt = f"""Here is your Moltbook dashboard (/home):

<home>
{_dumps(home)}
</home>

New posts in your feed you haven't engaged with yet:
<new_posts>
{_dumps(new_posts)}
</new_posts>

Your recent posts (avoid repetition):
<recent_own_posts>
{_dumps(recent_own_posts)}
</recent_own_posts>

Your stats: karma={agent_state.get("karma", 0)}, total_posts={agent_state.get("post_count", 0)}

Priority order:
1. Reply to any activity on your own posts (shown in home.activity_on_your_posts)
2. Engage with new_posts: comment, upvote, or skip each one
3. If you have something original to say not covered by any post, create one

Use the available tools to take your actions."""

    response = await client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=TOOLS,
        messages=[{"role": "user", "content": prompt}],
    )

    actions = []
    for block in response.content:
        if block.type == "tool_use":
            actions.append({"tool": block.name, "input": block.input})

    logger.info(
        "Claude decided %d actions (input_tokens=%d, cache_read=%d)",
        len(actions),
        response.usage.input_tokens,
        getattr(response.usage, "cache_read_input_tokens", 0),
    )
    return actions


async def solve_verification_challenge(challenge_text: str) -> str:
    """Parse and solve the obfuscated math problem in a Moltbook verification challenge.

    Challenges look like: "A] lO^bSt-Er S[wImS aT/ tW]eNn-Tyy mE^tE[rS aNd] SlO/wS bY^ fI[vE"
    which means: "a lobster swims at twenty meters and slows by five" → 20 - 5 = 15.00
    Answer must be a number with exactly 2 decimal places.
    """
    response = await client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": (
                    "Solve this Moltbook verification challenge. "
                    "It's a math word problem obfuscated with alternating caps and random symbols. "
                    "Strip the noise, read the plain sentence, do the arithmetic, "
                    "and reply with ONLY the numeric answer with exactly 2 decimal places (e.g. '15.00').\n\n"
                    f"Challenge: {challenge_text}"
                ),
            }
        ],
    )
    answer = response.content[0].text.strip()
    # Ensure 2 decimal places
    try:
        answer = f"{float(answer):.2f}"
    except ValueError:
        logger.warning("Could not parse verification answer '%s', using as-is", answer)
    return answer
