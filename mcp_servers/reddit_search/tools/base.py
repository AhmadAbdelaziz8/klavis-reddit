import os
import logging
from typing import Dict, List, TypedDict
import time
import random
import re
import asyncio

import asyncpraw
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# load the reddit api key
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "klavis-mcp/0.1 (+https://klavis.ai)")

class RedditClient:
    """A singleton wrapper for the asyncpraw.Reddit client."""
    _instance: "asyncpraw.Reddit|None" = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> "asyncpraw.Reddit":
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
                        raise ValueError("REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set")
                    
                    logger.info("Initializing Reddit client...")
                    cls._instance = asyncpraw.Reddit(
                        client_id=REDDIT_CLIENT_ID,
                        client_secret=REDDIT_CLIENT_SECRET,
                        user_agent=REDDIT_USER_AGENT,
                    )
        return cls._instance

# Lifecycle helpers to integrate with server startup/shutdown
async def init_http_clients() -> None:
    await RedditClient.get_instance()

async def close_http_clients() -> None:
    client = await RedditClient.get_instance()
    if client and client._core._requestor and client._core._requestor._http:
        await client._core._requestor._http.close()

_STOPWORDS = {
    "the", "a", "an", "and", "or", "vs", "vs.", "to", "for", "of", "on", "in", "with",
    "is", "are", "be", "by", "from", "about", "between",
}


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value or "")).strip().lower()


def tokenize(value: str) -> list[str]:
    norm = normalize_text(value)
    tokens = [t for t in norm.split() if t and t not in _STOPWORDS]
    return tokens


def generate_variants(tokens: list[str]) -> list[str]:
    # Create simple variants like joined tokens e.g., ["claude", "code"] -> "claudecode"
    variants: list[str] = []
    if len(tokens) >= 2:
        variants.append("".join(tokens))
        variants.append("-".join(tokens))
    # Add common brand variants heuristically
    joined = " ".join(tokens)
    if "cursor" in joined and "ai" in joined and "cursorai" not in variants:
        variants.append("cursorai")
        variants.append("cursor ai")
    if "claude" in joined and "code" in joined and "claudecode" not in variants:
        variants.append("claudecode")
        variants.append("claude code")
    return [v for v in variants if v]


def build_broad_query(query: str) -> str:
    """Build a broader Reddit search query using OR groups and variants.

    If the query looks like a comparison (contains 'vs'), we split into two
    groups and AND them to emphasize posts mentioning both sides.
    """
    text = normalize_text(query)
    parts = re.split(r"\bvs\.?\b", text)
    groups: list[list[str]] = []
    for part in parts:
        toks = tokenize(part)
        if not toks:
            continue
        variants = generate_variants(toks)
        # Group as OR terms inside parentheses
        or_terms = toks + variants
        # Escape quotes inside each term for Reddit search
        group = [f'"{term}"' if " " in term else term for term in or_terms]
        groups.append(group)

    if not groups:
        return text

    if len(groups) == 1:
        return "(" + " OR ".join(groups[0]) + ")"
    # Multiple groups -> AND them
    return " AND ".join("(" + " OR ".join(g) + ")" for g in groups)


def compute_semantic_score(query: str, title: str, selftext: str) -> float:
    """Score semantic relatedness via token overlap with light heuristics.

    Higher weight to title matches; small bonus if both sides of a 'vs' query appear.
    """
    query_tokens = set(tokenize(query))
    title_tokens = set(tokenize(title))
    body_tokens = set(tokenize(selftext))

    if not query_tokens:
        return 0.0

    title_overlap = len(query_tokens & title_tokens)
    body_overlap = len(query_tokens & body_tokens)

    score = title_overlap * 2.0 + body_overlap * 1.0

    # If it is a comparison query, ensure both sides appear
    parts = re.split(r"\bvs\.?\b", normalize_text(query))
    if len(parts) >= 2:
        side_scores = []
        for p in parts[:2]:
            toks = set(tokenize(p))
            side_scores.append(len(toks & (title_tokens | body_tokens)) > 0)
        if all(side_scores):
            score += 2.0

    return float(score)


# Define the structure of the returned data
class SubredditInfo(TypedDict):
    """Structured data for a single subreddit."""
    name: str
    subscriber_count: int
    description: str


class PostInfo(TypedDict):
    """Structured data for a Reddit post summary."""
    id: str
    subreddit: str
    title: str
    score: int
    url: str
    comment_count: int


class CommentInfo(TypedDict):
    """Structured data for a single comment."""
    author: str
    text: str
    score: int


class PostDetails(TypedDict):
    """The combined structure for a post and its top comments."""
    title: str
    author: str
    text: str
    score: int
    top_comments: List[CommentInfo]