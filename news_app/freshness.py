from datetime import datetime, timedelta
from dateutil import parser
from loguru import logger
from typing import Dict, Any
from news_app.content_types import ContentType

def is_stale(headline: Dict[str, Any], content_type: ContentType) -> bool:
    """
    Check if the source article is too old to be published.
    Returns True if stale, False if fresh or unknown.
    """
    pub_date_str = headline.get("published_at")
    if not pub_date_str:
        return False # unknown, assume fresh for now
        
    try:
        pub_date = parser.parse(pub_date_str)
        # remove tzinfo for safe comparison if necessary, but datetime.utcnow() is naive
        if pub_date.tzinfo is not None:
            pub_date = pub_date.astimezone(None).replace(tzinfo=None)
            
        age = datetime.utcnow() - pub_date
        
        # Max age thresholds
        limits = {
            ContentType.HARD_NEWS: timedelta(days=2),
            ContentType.MATCH_REPORT: timedelta(days=2),
            ContentType.ANALYSIS_EXPLAINER: timedelta(days=7),
            ContentType.RECOMMENDATION_ARTICLE: timedelta(days=30)
        }
        
        limit = limits.get(content_type, timedelta(days=2))
        
        if age > limit:
            logger.warning(f"Source article is stale (age: {age.days} days, limit: {limit.days})")
            return True
            
        return False
    except Exception as e:
        logger.debug(f"Could not check freshness: {e}")
        return False
