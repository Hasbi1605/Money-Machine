from datetime import datetime, timedelta
from dateutil import parser
from loguru import logger
from typing import Dict, Any
from news_app.content_types import ContentType

def is_stale(headline: Dict[str, Any], content_type: ContentType, category: str = "") -> bool:
    """
    Check if the source article is too old to be published.
    Returns True if stale, False if fresh or unknown.
    """
    pub_date_str = headline.get("published_at")
    if not pub_date_str:
        return False # unknown, assume fresh for now
        
    try:
        pub_date = parser.parse(pub_date_str)
        # convert everything to offset-naive UTC to safely compare
        if pub_date.tzinfo is not None:
            pub_date = pub_date.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            
        now_utc = datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        age = now_utc - pub_date
        
        # Base Max age thresholds
        limits = {
            ContentType.HARD_NEWS: timedelta(days=2),
            ContentType.MATCH_REPORT: timedelta(days=2),
            ContentType.ANALYSIS_EXPLAINER: timedelta(days=7),
            ContentType.RECOMMENDATION_ARTICLE: timedelta(days=30)
        }
        
        # Category-aware overrides
        if category.lower() in ["bola", "olahraga", "sports"]:
            limits[ContentType.HARD_NEWS] = timedelta(days=1)
            limits[ContentType.MATCH_REPORT] = timedelta(days=1)
            
        if category.lower() in ["ekonomi", "finance"]:
            # Financial news moves fast
            limits[ContentType.HARD_NEWS] = timedelta(hours=36)
            
        limit = limits.get(content_type, timedelta(days=2))
        
        if age > limit:
            logger.warning(f"Source article '{category}' is stale (age: {age.days}d {age.seconds//3600}h, limit: {limit.days}d {limit.seconds//3600}h)")
            return True
            
        return False
    except Exception as e:
        logger.debug(f"Could not check freshness format: {e}")
        return False
