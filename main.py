"""
AI Money Machine - Main Runner
Central scheduler that runs all automation pipelines on schedule.

Usage:
    python main.py                  # Run all pipelines on schedule
    python main.py --blog           # Run blog pipeline once
    python main.py --video          # Run video pipeline once
    python main.py --saas           # Start SaaS server only
    python main.py --dashboard      # Start dashboard only
    python main.py --all-servers    # Start SaaS + Dashboard servers
"""

import asyncio
import argparse
import signal
import sys
from datetime import datetime

from loguru import logger

from shared.config import settings
from shared.database import init_db, get_stats
from shared.notifier import notifier
from shared.logger import setup_logging


async def run_blog_once():
    """Run the blog pipeline once."""
    from blog_engine.orchestrator import run_blog_cycle
    logger.info("🚀 Running blog pipeline (one-time)")
    return await run_blog_cycle()


async def run_video_once():
    """Run the video pipeline once."""
    from video_engine.orchestrator import run_video_cycle
    logger.info("🚀 Running video pipeline (one-time)")
    return await run_video_cycle()


def start_saas_server():
    """Start the Micro-SaaS FastAPI server."""
    import uvicorn
    from saas_app.app import app

    logger.info(f"🌐 Starting SaaS server on {settings.saas.host}:{settings.saas.port}")
    uvicorn.run(
        app,
        host=settings.saas.host,
        port=settings.saas.port,
        log_level="info",
    )


def start_dashboard_server():
    """Start the dashboard server."""
    import uvicorn
    from dashboard.app import dashboard_app

    port = settings.saas.port + 1  # Dashboard on next port
    logger.info(f"📊 Starting dashboard on {settings.saas.host}:{port}")
    uvicorn.run(
        dashboard_app,
        host=settings.saas.host,
        port=port,
        log_level="info",
    )


async def send_daily_report():
    """Send daily stats report via Telegram."""
    stats = await get_stats()
    await notifier.send_daily_report(stats)
    logger.info(f"📊 Daily report sent: {stats}")


async def run_scheduled():
    """
    Run all pipelines on schedule using APScheduler.
    
    Schedule:
    - Blog pipeline: Every 12 hours (2 articles/day per language)
    - Video pipeline: Every 24 hours (1 video/day per language)
    - Daily report: Every day at midnight
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger

    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    # Blog pipeline - every 12 hours
    scheduler.add_job(
        run_blog_once,
        IntervalTrigger(hours=12),
        id="blog_pipeline",
        name="Blog Article Generation",
        next_run_time=datetime.now(),  # Run immediately on start
    )

    # Video pipeline - every 24 hours
    scheduler.add_job(
        run_video_once,
        IntervalTrigger(hours=24),
        id="video_pipeline",
        name="Video Generation",
    )

    # Daily report - every day at 23:59
    scheduler.add_job(
        send_daily_report,
        CronTrigger(hour=23, minute=59),
        id="daily_report",
        name="Daily Stats Report",
    )

    scheduler.start()
    logger.info("📅 Scheduler started with the following jobs:")
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.name}: next run at {job.next_run_time}")

    # Send startup notification
    await notifier.send(
        "🚀 <b>AI Money Machine Started!</b>\n"
        f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"🌐 Languages: {', '.join(settings.get_languages())}\n"
        f"📝 Blog: Every 12 hours\n"
        f"🎬 Video: Every 24 hours\n"
        f"📊 Report: Daily at 23:59"
    )

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler stopped")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="AI Money Machine")
    parser.add_argument("--blog", action="store_true", help="Run blog pipeline once")
    parser.add_argument("--video", action="store_true", help="Run video pipeline once")
    parser.add_argument("--saas", action="store_true", help="Start SaaS server only")
    parser.add_argument("--dashboard", action="store_true", help="Start dashboard only")
    parser.add_argument("--all-servers", action="store_true", help="Start SaaS + Dashboard")
    parser.add_argument("--report", action="store_true", help="Send daily report now")

    args = parser.parse_args()

    # Initialize
    setup_logging()
    await init_db()
    settings.ensure_dirs()

    logger.info("=" * 50)
    logger.info("🤖 AI Money Machine v1.0")
    logger.info("=" * 50)

    if args.blog:
        await run_blog_once()
    elif args.video:
        await run_video_once()
    elif args.saas:
        start_saas_server()
    elif args.dashboard:
        start_dashboard_server()
    elif args.all_servers:
        import multiprocessing
        saas_proc = multiprocessing.Process(target=start_saas_server)
        dash_proc = multiprocessing.Process(target=start_dashboard_server)
        saas_proc.start()
        dash_proc.start()
        logger.info("Both servers started. Press Ctrl+C to stop.")
        try:
            saas_proc.join()
            dash_proc.join()
        except KeyboardInterrupt:
            saas_proc.terminate()
            dash_proc.terminate()
    elif args.report:
        await send_daily_report()
    else:
        # Default: run full scheduler
        await run_scheduled()


if __name__ == "__main__":
    asyncio.run(main())
