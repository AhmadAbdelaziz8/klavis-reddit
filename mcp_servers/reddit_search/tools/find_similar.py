import logging
from typing import List

from .base import RedditClient, PostInfo, build_broad_query, compute_semantic_score

logger = logging.getLogger(__name__)


async def find_similar_posts_reddit(post_id: str, limit: int = 10) -> List[PostInfo]:
    """Find posts similar to the given post using its title as a query."""
    reddit = await RedditClient.get_instance()
    
    # 1) Get the original post's details
    try:
        original_post = await reddit.submission(id=post_id)
        await original_post.load()
        title = original_post.title
        subreddit_name = original_post.subreddit.display_name
    except Exception as exc:
        raise ValueError(f"Post with ID '{post_id}' not found or could not be loaded: {exc}")

    broad_q = build_broad_query(title)
    scored: list[tuple[float, PostInfo]] = []

    # 2) Search in the same subreddit
    try:
        subreddit = await reddit.subreddit(subreddit_name)
        async for post in subreddit.search(broad_q, sort="relevance", limit=max(limit, 5)):
            if post.id == post_id:
                continue
            pi = PostInfo(
                id=post.id, subreddit=post.subreddit.display_name, title=post.title,
                score=post.score, url=post.url, comment_count=post.num_comments
            )
            sem = compute_semantic_score(title, pi["title"], post.selftext)
            if sem > 0:
                scored.append((sem, pi))
    except Exception as exc:
        logger.warning(f"Subreddit-scope similar search failed: {exc}")

    # 3) Site-wide search
    try:
        all_subreddit = await reddit.subreddit("all")
        async for post in all_subreddit.search(broad_q, sort="relevance", limit=max(limit, 10)):
            if post.id == post_id:
                continue
            pi = PostInfo(
                id=post.id, subreddit=post.subreddit.display_name, title=post.title,
                score=post.score, url=post.url, comment_count=post.num_comments
            )
            sem = compute_semantic_score(title, pi["title"], post.selftext)
            if sem > 0:
                scored.append((sem, pi))
    except Exception as exc:
        logger.warning(f"Site-wide similar search failed: {exc}")

    # 4) Rank and deduplicate
    results: list[PostInfo] = []
    seen: set[str] = set()
    for _, pi in sorted(scored, key=lambda x: (x[0], x[1]["score"]), reverse=True):
        if not pi["id"] or pi["id"] in seen:
            continue
        seen.add(pi["id"])
        results.append(pi)
        if len(results) >= limit:
            break
            
    return results
