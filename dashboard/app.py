"""
Dashboard - Simple monitoring web UI for all pipelines.
Shows stats, recent runs, errors, and revenue tracking.
"""

from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from loguru import logger

from shared.database import get_stats, DB_PATH

import aiosqlite

dashboard_app = FastAPI(title="AI Money Machine Dashboard")


@dashboard_app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page."""
    stats = await get_stats()

    # Get recent pipeline runs
    recent_runs = []
    recent_articles = []
    recent_videos = []

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            rows = await db.execute_fetchall(
                "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 20"
            )
            recent_runs = [dict(r) for r in rows]

            rows = await db.execute_fetchall(
                "SELECT * FROM articles ORDER BY created_at DESC LIMIT 10"
            )
            recent_articles = [dict(r) for r in rows]

            rows = await db.execute_fetchall(
                "SELECT * FROM videos ORDER BY created_at DESC LIMIT 10"
            )
            recent_videos = [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Dashboard DB error: {e}")

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI Money Machine - Dashboard</title>
        <meta http-equiv="refresh" content="60">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #0a0a1a; color: #e0e0e0;
            }}
            .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
            h1 {{
                font-size: 1.8rem; padding: 20px 0;
                background: linear-gradient(90deg, #00d2ff, #7b2ff7);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            }}
            .stats-grid {{
                display: grid; grid-template-columns: repeat(4, 1fr);
                gap: 15px; margin: 20px 0;
            }}
            .stat-card {{
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 12px; padding: 25px; text-align: center;
            }}
            .stat-value {{ font-size: 2.5rem; font-weight: bold; color: #fff; }}
            .stat-label {{ color: #888; font-size: 0.85rem; margin-top: 5px; }}
            .section {{ margin: 30px 0; }}
            .section h2 {{ font-size: 1.3rem; color: #fff; margin-bottom: 15px; }}
            table {{
                width: 100%; border-collapse: collapse;
                background: rgba(255,255,255,0.03);
                border-radius: 10px; overflow: hidden;
            }}
            th {{ background: rgba(123,47,247,0.2); padding: 12px; text-align: left; font-size: 0.85rem; }}
            td {{ padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem; }}
            .status-success {{ color: #4caf50; }}
            .status-error {{ color: #f44336; }}
            .status-running {{ color: #ffc107; }}
            .timestamp {{ color: #666; font-size: 0.8rem; }}
            @media (max-width: 768px) {{
                .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 AI Money Machine Dashboard</h1>
            <p style="color:#666; margin-bottom: 20px;">
                Auto-refreshes every 60 seconds | Last update: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC
            </p>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{stats.get('total_articles', 0)}</div>
                    <div class="stat-label">📝 Total Articles</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats.get('total_videos', 0)}</div>
                    <div class="stat-label">🎬 Total Videos</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats.get('runs_today', 0)}</div>
                    <div class="stat-label">🔄 Runs Today</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color: {'#f44336' if stats.get('errors_today', 0) > 0 else '#4caf50'}">
                        {stats.get('errors_today', 0)}
                    </div>
                    <div class="stat-label">⚠️ Errors Today</div>
                </div>
            </div>

            <div class="section">
                <h2>🔄 Recent Pipeline Runs</h2>
                <table>
                    <tr><th>Pipeline</th><th>Status</th><th>Items</th><th>Started</th><th>Error</th></tr>
                    {"".join(f'''
                    <tr>
                        <td>{r.get('pipeline', '')}</td>
                        <td class="status-{r.get('status', '')}">{'✅' if r.get('status') == 'success' else '❌' if r.get('status') == 'error' else '⏳'} {r.get('status', '')}</td>
                        <td>{r.get('items_produced', 0)}</td>
                        <td class="timestamp">{r.get('started_at', '')}</td>
                        <td style="color:#f44336;max-width:200px;overflow:hidden;text-overflow:ellipsis;">{r.get('error_message', '') or '-'}</td>
                    </tr>''' for r in recent_runs)}
                </table>
            </div>

            <div class="section">
                <h2>📝 Recent Articles</h2>
                <table>
                    <tr><th>Title</th><th>Keyword</th><th>Platform</th><th>Language</th><th>Words</th><th>Date</th></tr>
                    {"".join(f'''
                    <tr>
                        <td>{a.get('title', '')[:50]}</td>
                        <td>{a.get('keyword', '')}</td>
                        <td>{a.get('platform', '')}</td>
                        <td>{a.get('language', '')}</td>
                        <td>{a.get('word_count', 0)}</td>
                        <td class="timestamp">{a.get('created_at', '')}</td>
                    </tr>''' for a in recent_articles)}
                </table>
            </div>

            <div class="section">
                <h2>🎬 Recent Videos</h2>
                <table>
                    <tr><th>Title</th><th>Niche</th><th>Platform</th><th>Duration</th><th>Date</th></tr>
                    {"".join(f'''
                    <tr>
                        <td>{v.get('title', '')[:50]}</td>
                        <td>{v.get('niche', '')}</td>
                        <td>{v.get('platform', '')}</td>
                        <td>{v.get('duration_seconds', 0):.0f}s</td>
                        <td class="timestamp">{v.get('created_at', '')}</td>
                    </tr>''' for v in recent_videos)}
                </table>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@dashboard_app.get("/api/stats")
async def api_stats():
    """JSON stats endpoint."""
    return await get_stats()
