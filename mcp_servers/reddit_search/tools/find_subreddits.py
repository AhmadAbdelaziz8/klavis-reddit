import logging
from typing import List

from .base import RedditClient, SubredditInfo


logger = logging.getLogger(__name__)


async def find_relevant_subreddits(query: str, limit: int = 10) -> List[SubredditInfo]:
    """Find subreddits relevant to the query."""
    logger.info(f"Searching for subreddits with query: '{query}'")
    reddit = await RedditClient.get_instance()
    
    results = []
    async for subreddit in reddit.subreddits.search(query, limit=limit):
        results.append(
            SubredditInfo(
                name=subreddit.display_name,
                subscriber_count=subreddit.subscribers,
                description=subreddit.public_description or "No description provided.",
            )
        )
    return results
