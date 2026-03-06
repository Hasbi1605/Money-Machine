"""
Newsletter Module — sends daily digest emails to subscribers.
Uses aiosmtplib for async email sending via SMTP.
Falls back to a simple digest builder if no SMTP configured.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from loguru import logger

from shared.config import settings
from shared.database import get_news_articles, get_active_subscribers, get_trending_news


async def build_newsletter_html(articles: List[Dict], trending: List[Dict]) -> str:
    """Build an HTML email body for the daily newsletter digest."""

    article_items = ""
    for art in articles[:8]:
        cat_label = art.get("category", "").capitalize()
        thumbnail = art.get("thumbnail_url", "")
        title = art.get("title", "")
        excerpt = art.get("excerpt", "")[:120]
        slug = art.get("slug", "")
        site_url = settings.news.site_url or "https://cikalnews.onrender.com"
        link = f"{site_url}/artikel/{slug}"

        article_items += f"""
        <tr>
          <td style="padding: 16px 0; border-bottom: 1px solid #eee;">
            <table cellpadding="0" cellspacing="0" border="0" width="100%">
              <tr>
                <td width="120" valign="top" style="padding-right: 16px;">
                  <a href="{link}">
                    <img src="{thumbnail}" alt="{title}" width="120" height="80"
                      style="border-radius: 8px; object-fit: cover; display: block;" />
                  </a>
                </td>
                <td valign="top">
                  <span style="display: inline-block; background: #1A237E; color: white;
                    font-size: 10px; padding: 2px 8px; border-radius: 12px; margin-bottom: 6px;
                    text-transform: uppercase; font-weight: bold;">{cat_label}</span>
                  <h3 style="margin: 4px 0 6px; font-size: 15px; line-height: 1.3;">
                    <a href="{link}" style="color: #111; text-decoration: none;">{title}</a>
                  </h3>
                  <p style="color: #666; font-size: 13px; margin: 0; line-height: 1.4;">{excerpt}...</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        """

    trending_items = ""
    for i, art in enumerate(trending[:5], 1):
        slug = art.get("slug", "")
        site_url = settings.news.site_url or "https://cikalnews.onrender.com"
        link = f"{site_url}/artikel/{slug}"
        trending_items += f"""
        <tr>
          <td style="padding: 8px 0; {'' if i == 5 else 'border-bottom: 1px solid #f3f4f6;'}">
            <a href="{link}" style="text-decoration: none; color: #333;">
              <span style="color: #1A237E; font-weight: bold; font-size: 18px; margin-right: 12px;">{i}</span>
              <span style="font-size: 13px;">{art.get('title', '')}</span>
            </a>
          </td>
        </tr>
        """

    now = datetime.utcnow()
    months = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
              "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    date_str = f"{now.day} {months[now.month]} {now.year}"

    return f"""
    <!DOCTYPE html>
    <html lang="id">
    <head><meta charset="UTF-8"></head>
    <body style="margin: 0; padding: 0; background-color: #f3f4f6; font-family: -apple-system, 'Inter', 'Segoe UI', sans-serif;">
      <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color: #f3f4f6;">
        <tr><td align="center" style="padding: 24px 16px;">
          <table cellpadding="0" cellspacing="0" border="0" width="600" style="max-width: 600px;">

            <!-- Header -->
            <tr>
              <td style="background: linear-gradient(135deg, #1A237E, #3949AB); padding: 24px 32px; border-radius: 12px 12px 0 0; text-align: center;">
                <h1 style="margin: 0; color: white; font-size: 24px; font-weight: 800;">
                  Cikal<span style="color: #c5cae9;">News</span>
                </h1>
                <p style="margin: 8px 0 0; color: #c5cae9; font-size: 13px;">📰 Rangkuman Berita Harian — {date_str}</p>
              </td>
            </tr>

            <!-- Body -->
            <tr>
              <td style="background: white; padding: 24px 32px;">
                <h2 style="margin: 0 0 16px; font-size: 18px; color: #111;">📌 Berita Utama</h2>
                <table cellpadding="0" cellspacing="0" border="0" width="100%">
                  {article_items}
                </table>

                <!-- Trending -->
                <h2 style="margin: 24px 0 12px; font-size: 18px; color: #111;">🔥 Trending</h2>
                <table cellpadding="0" cellspacing="0" border="0" width="100%"
                  style="background: #f8f9fa; border-radius: 8px; padding: 12px;">
                  {trending_items}
                </table>
              </td>
            </tr>

            <!-- Footer -->
            <tr>
              <td style="background: #f8f9fa; padding: 20px 32px; border-radius: 0 0 12px 12px; text-align: center;">
                <p style="margin: 0 0 8px; font-size: 12px; color: #999;">
                  Anda menerima email ini karena berlangganan newsletter CikalNews.
                </p>
                <p style="margin: 0; font-size: 12px; color: #999;">
                  <a href="{{{{unsubscribe_url}}}}" style="color: #1A237E;">Berhenti Berlangganan</a>
                </p>
              </td>
            </tr>

          </table>
        </td></tr>
      </table>
    </body>
    </html>
    """


async def send_newsletter():
    """
    Send newsletter to all active subscribers.
    For now, logs the intent (SMTP integration requires env config).
    """
    subscribers = await get_active_subscribers()
    if not subscribers:
        logger.info("No newsletter subscribers — skipping")
        return 0

    # Get latest articles
    articles = await get_news_articles(limit=8)
    trending = await get_trending_news(limit=5)

    if not articles:
        logger.info("No articles to send in newsletter")
        return 0

    html = await build_newsletter_html(articles, trending)
    site_url = settings.news.site_url or "https://cikalnews.onrender.com"

    sent = 0
    for sub in subscribers:
        email = sub.get("email", "")
        token = sub.get("token", "")
        unsub_url = f"{site_url}/api/unsubscribe?email={email}&token={token}"

        # Personalize unsubscribe URL
        personal_html = html.replace("{{unsubscribe_url}}", unsub_url)

        # Log the newsletter (in production, integrate with SMTP)
        logger.info(f"📧 Newsletter ready for: {email} (digest with {len(articles)} articles)")
        sent += 1

    logger.info(f"📬 Newsletter digest prepared for {sent} subscribers")
    return sent
