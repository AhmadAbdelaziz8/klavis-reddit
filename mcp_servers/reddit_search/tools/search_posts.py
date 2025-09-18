import logging
from typing import List, Literal

from .base import RedditClient, PostInfo, build_broad_query, compute_semantic_score

logger = logging.getLogger(__name__)

SortOrder = Literal["relevance", "hot", "top", "new", "comments"]
TimeFilter = Literal["all", "day", "hour", "month", "week", "year"]

async def search_subreddit_posts(
    subreddit_name: str, 
    query: str, 
    limit: int = 10,
    sort: SortOrder = "relevance",
    time_filter: TimeFilter = "all",
    advanced_query: str = ""
) -> List[PostInfo]:
    """Search for posts in a subreddit with advanced filtering."""
    subreddit_name = subreddit_name.strip().lstrip("r/").lower()
    query = query.strip()
    
    # Combine the generated broad query with any advanced syntax provided
    broad_q = build_broad_query(query)
    final_query = f"({broad_q}) AND ({advanced_query})" if advanced_query else broad_q
    
    reddit = await RedditClient.get_instance()
    subreddit = await reddit.subreddit(subreddit_name)
    
    scored: list[tuple[float, PostInfo]] = []

    try:
        search_results = subreddit.search(final_query, sort=sort, time_filter=time_filter, limit=max(limit, 50))
        async for post in search_results:
            pi = PostInfo(
                id=post.id,
                subreddit=post.subreddit.display_name,
                title=post.title,
                score=post.score,
                url=post.url,
                comment_count=post.num_comments,
            )
            sem_score = compute_semantic_score(query, pi["title"], post.selftext)
            scored.append((sem_score, pi))
    except Exception as exc:
        logger.error(f"Subreddit search failed for query '{final_query}': {exc}")
        return []

    # Rank and deduplicate
    matching_posts: list[PostInfo] = []
    seen: set[str] = set()
    for _, pi in sorted(scored, key=lambda x: (x[0], x[1]["score"]), reverse=True):
        if not pi["id"] or pi["id"] in seen:
            continue
        seen.add(pi["id"])
        matching_posts.append(pi)
        if len(matching_posts) >= limit:
            break
            
    return matching_posts
