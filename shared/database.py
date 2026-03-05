"""
SQLite database for tracking all generated content, stats, errors.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import aiosqlite
from loguru import logger

from shared.config import settings

DB_PATH = settings.data_dir / "money_machine.db"


async def init_db():
    """Initialize the database tables."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                slug TEXT,
                keyword TEXT,
                language TEXT DEFAULT 'en',
                platform TEXT,
                platform_url TEXT,
                word_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                published_at TIMESTAMP,
                affiliate_links_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                script_length INTEGER DEFAULT 0,
                language TEXT DEFAULT 'en',
                platform TEXT,
                platform_id TEXT,
                platform_url TEXT,
                duration_seconds REAL DEFAULT 0,
                status TEXT DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                uploaded_at TIMESTAMP,
                niche TEXT
            );

            CREATE TABLE IF NOT EXISTS social_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                language TEXT DEFAULT 'id',
                niche TEXT,
                platforms TEXT,
                image_path TEXT,
                status TEXT DEFAULT 'created',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS saas_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                plan TEXT DEFAULT 'free',
                uses_today INTEGER DEFAULT 0,
                total_uses INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS revenue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                amount REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                description TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pipeline TEXT NOT NULL,
                status TEXT DEFAULT 'running',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                items_produced INTEGER DEFAULT 0,
                error_message TEXT
            );

            CREATE TABLE IF NOT EXISTS news_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                slug TEXT UNIQUE,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                excerpt TEXT,
                meta_description TEXT,
                tags TEXT,
                thumbnail_url TEXT,
                source_title TEXT,
                source_url TEXT,
                source_name TEXT,
                views INTEGER DEFAULT 0,
                status TEXT DEFAULT 'published',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                published_at TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_news_category ON news_articles(category);
            CREATE INDEX IF NOT EXISTS idx_news_slug ON news_articles(slug);
            CREATE INDEX IF NOT EXISTS idx_news_status ON news_articles(status);
            CREATE INDEX IF NOT EXISTS idx_news_created ON news_articles(created_at DESC);
        """)
        await db.commit()
        logger.info("Database initialized")


async def log_article(
    title: str, keyword: str, language: str, platform: str,
    platform_url: str = "", word_count: int = 0
) -> int:
    """Log a published article."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO articles (title, keyword, language, platform, platform_url, 
               word_count, status, published_at)
               VALUES (?, ?, ?, ?, ?, ?, 'published', ?)""",
            (title, keyword, language, platform, platform_url, word_count,
             datetime.utcnow().isoformat())
        )
        await db.commit()
        return cursor.lastrowid


async def log_video(
    title: str, language: str, platform: str, niche: str,
    duration_seconds: float = 0, platform_url: str = ""
) -> int:
    """Log an uploaded video."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO videos (title, language, platform, niche, duration_seconds,
               platform_url, status, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, 'uploaded', ?)""",
            (title, language, platform, niche, duration_seconds, platform_url,
             datetime.utcnow().isoformat())
        )
        await db.commit()
        return cursor.lastrowid


async def log_social_post(
    title: str, language: str, niche: str,
    platforms: str = "", image_path: str = ""
) -> int:
    """Log a generated social post."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO social_posts (title, language, niche, platforms, image_path, status)
               VALUES (?, ?, ?, ?, ?, 'created')""",
            (title, language, niche, platforms, image_path)
        )
        await db.commit()
        return cursor.lastrowid


async def log_pipeline_run(pipeline: str) -> int:
    """Start a pipeline run log."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO pipeline_runs (pipeline) VALUES (?)", (pipeline,)
        )
        await db.commit()
        return cursor.lastrowid


async def finish_pipeline_run(run_id: int, items: int = 0, error: str = ""):
    """Finish a pipeline run log."""
    status = "error" if error else "success"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE pipeline_runs SET status=?, finished_at=?, items_produced=?, error_message=?
               WHERE id=?""",
            (status, datetime.utcnow().isoformat(), items, error, run_id)
        )
        await db.commit()


async def add_premium_user(email: str, plan: str = "pro") -> int:
    """Add or upgrade a user to premium."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO saas_users (email, plan, created_at)
               VALUES (?, ?, ?)
               ON CONFLICT(email) DO UPDATE SET plan=?""",
            (email, plan, datetime.utcnow().isoformat(), plan)
        )
        await db.commit()
        logger.info(f"Premium user added/updated: {email} -> {plan}")
        return 1


async def is_premium_user(email: str) -> bool:
    """Check if a user has premium access."""
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchall(
            "SELECT plan FROM saas_users WHERE email=? AND plan != 'free'",
            (email,)
        )
        return bool(row)


async def log_revenue(source: str, amount: float, currency: str = "USD", description: str = ""):
    """Log a revenue event."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO revenue (source, amount, currency, description) VALUES (?, ?, ?, ?)",
            (source, amount, currency, description)
        )
        await db.commit()
        logger.info(f"Revenue logged: {source} ${amount} {currency}")


async def get_stats() -> Dict[str, Any]:
    """Get overall statistics."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        articles = await db.execute_fetchall("SELECT COUNT(*) as c FROM articles WHERE status='published'")
        social = await db.execute_fetchall("SELECT COUNT(*) as c FROM social_posts")
        news = await db.execute_fetchall("SELECT COUNT(*) as c FROM news_articles WHERE status='published'")
        errors = await db.execute_fetchall(
            "SELECT COUNT(*) as c FROM pipeline_runs WHERE status='error' AND date(started_at) = date('now')"
        )
        runs_today = await db.execute_fetchall(
            "SELECT COUNT(*) as c FROM pipeline_runs WHERE date(started_at) = date('now')"
        )

        return {
            "total_articles": articles[0][0] if articles else 0,
            "total_social_posts": social[0][0] if social else 0,
            "total_news": news[0][0] if news else 0,
            "errors_today": errors[0][0] if errors else 0,
            "runs_today": runs_today[0][0] if runs_today else 0,
        }


# ── News Article DB helpers ───────────────────────────────────

async def save_news_article(article: Dict) -> Optional[int]:
    """Save a news article to the database. Returns article ID or None on duplicate."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            tags = article.get("tags", [])
            if isinstance(tags, list):
                tags = ",".join(tags)

            cursor = await db.execute(
                """INSERT INTO news_articles
                   (title, slug, category, content, excerpt, meta_description,
                    tags, thumbnail_url, source_title, source_url, source_name,
                    status, published_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', ?)""",
                (
                    article["title"],
                    article["slug"],
                    article["category"],
                    article["content"],
                    article.get("excerpt", ""),
                    article.get("meta_description", ""),
                    tags,
                    article.get("thumbnail_url", ""),
                    article.get("source_title", ""),
                    article.get("source_url", ""),
                    article.get("source_name", ""),
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()
            logger.info(f"News saved: {article['title'][:50]}...")
            return cursor.lastrowid
        except Exception as e:
            if "UNIQUE" in str(e):
                logger.info(f"Duplicate slug skipped: {article.get('slug', '')}")
            else:
                logger.error(f"Error saving news: {e}")
            return None


async def get_news_articles(
    category: str = "",
    limit: int = 20,
    offset: int = 0,
) -> List[Dict]:
    """Get news articles, optionally filtered by category."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        if category:
            rows = await db.execute_fetchall(
                """SELECT * FROM news_articles
                   WHERE category=? AND status='published'
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (category, limit, offset),
            )
        else:
            rows = await db.execute_fetchall(
                """SELECT * FROM news_articles
                   WHERE status='published'
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (limit, offset),
            )

        return [dict(r) for r in rows]


async def get_news_by_slug(slug: str) -> Optional[Dict]:
    """Get a single news article by slug."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM news_articles WHERE slug=? AND status='published'",
            (slug,),
        )
        if rows:
            # Increment view count
            await db.execute(
                "UPDATE news_articles SET views = views + 1 WHERE slug=?",
                (slug,),
            )
            await db.commit()
            return dict(rows[0])
        return None


async def get_news_count(category: str = "") -> int:
    """Count published news articles."""
    async with aiosqlite.connect(DB_PATH) as db:
        if category:
            rows = await db.execute_fetchall(
                "SELECT COUNT(*) FROM news_articles WHERE category=? AND status='published'",
                (category,),
            )
        else:
            rows = await db.execute_fetchall(
                "SELECT COUNT(*) FROM news_articles WHERE status='published'"
            )
        return rows[0][0] if rows else 0


async def get_related_news(category: str, exclude_slug: str, limit: int = 4) -> List[Dict]:
    """Get related articles from the same category."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT * FROM news_articles
               WHERE category=? AND slug!=? AND status='published'
               ORDER BY created_at DESC LIMIT ?""",
            (category, exclude_slug, limit),
        )
        return [dict(r) for r in rows]


async def get_trending_news(limit: int = 10) -> List[Dict]:
    """Get most viewed articles."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT * FROM news_articles
               WHERE status='published'
               ORDER BY views DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in rows]


async def search_news(query: str, limit: int = 20) -> List[Dict]:
    """Search articles by title or content."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT * FROM news_articles
               WHERE status='published' AND (title LIKE ? OR content LIKE ?)
               ORDER BY created_at DESC LIMIT ?""",
            (f"%{query}%", f"%{query}%", limit),
        )
        return [dict(r) for r in rows]
