import logging
from typing import List, Optional
from asyncpraw.models import Comment, MoreComments


from .base import RedditClient, PostDetails, CommentInfo

logger = logging.getLogger(__name__)


async def _fetch_comments_recursive(
    comments: List[Comment | MoreComments], 
    depth: int, 
    limit: int, 
    current_depth: int = 1
) -> List[CommentInfo]:
    """Recursively fetch comments up to a specified depth."""
    if current_depth > depth or not comments:
        return []

    results: List[CommentInfo] = []
    for comment in comments:
        if isinstance(comment, MoreComments):
            continue
        
        results.append(
            CommentInfo(
                author=getattr(comment, 'author', '[deleted]'),
                text=comment.body,
                score=comment.score,
            )
        )
        if len(results) >= limit:
            return results
        
        if hasattr(comment, "replies"):
            replies = await _fetch_comments_recursive(
                comment.replies, depth, limit - len(results), current_depth + 1
            )
            results.extend(replies)
        
        if len(results) >= limit:
            return results
            
    return results


async def get_post_and_top_comments(
    post_id: str, 
    limit: int = 10, 
    sort: str = "top",
    depth: Optional[int] = 2
) -> PostDetails:
    """Gets post and comment details using PRAW, with controllable depth."""
    logger.info(f"Fetching post and comments for submission ID: {post_id} with depth={depth}")
    reddit = await RedditClient.get_instance()
    
    submission = await reddit.submission(id=post_id)
    await submission.load()
    
    submission.comment_sort = sort
    
    # Replace MoreComments objects to allow traversal
    await submission.comments.replace_more(limit=None)
    
    all_comments = await _fetch_comments_recursive(submission.comments, depth, limit)

    return PostDetails(
        title=submission.title,
        author=getattr(submission, 'author', '[deleted]'),
        text=submission.selftext or "[This post has no text content]",
        score=submission.score,
        top_comments=all_comments,
    )
