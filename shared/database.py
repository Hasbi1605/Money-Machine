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


async def get_stats() -> Dict[str, Any]:
    """Get overall statistics."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        articles = await db.execute_fetchall("SELECT COUNT(*) as c FROM articles WHERE status='published'")
        social = await db.execute_fetchall("SELECT COUNT(*) as c FROM social_posts")
        errors = await db.execute_fetchall(
            "SELECT COUNT(*) as c FROM pipeline_runs WHERE status='error' AND date(started_at) = date('now')"
        )
        runs_today = await db.execute_fetchall(
            "SELECT COUNT(*) as c FROM pipeline_runs WHERE date(started_at) = date('now')"
        )

        return {
            "total_articles": articles[0][0] if articles else 0,
            "total_social_posts": social[0][0] if social else 0,
            "errors_today": errors[0][0] if errors else 0,
            "runs_today": runs_today[0][0] if runs_today else 0,
        }
