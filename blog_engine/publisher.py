"""
Blog Publisher - Auto-publishes articles to WordPress, Medium, and Blogger.
"""

import json
import re
from typing import Optional, Dict
from datetime import datetime

from pathlib import Path

import aiohttp
from loguru import logger

from shared.config import settings


class WordPressPublisher:
    """Publish articles to WordPress via REST API."""

    def __init__(self):
        self.url = settings.wordpress.url.rstrip("/")
        self.username = settings.wordpress.username
        self.password = settings.wordpress.password
        self.enabled = bool(self.url and self.username and self.password)

    async def publish(self, article: Dict) -> Optional[str]:
        """Publish an article to WordPress. Returns the post URL."""
        if not self.enabled:
            logger.debug("WordPress publishing disabled (no credentials)")
            return None

        endpoint = f"{self.url}/wp-json/wp/v2/posts"

        # Convert markdown to HTML (basic)
        content = article.get("content", "")
        content_html = markdown_to_html(content)

        payload = {
            "title": article.get("title", "Untitled"),
            "content": content_html,
            "status": "publish",
            "slug": article.get("slug", ""),
            "excerpt": article.get("excerpt", ""),
            "meta": {
                "description": article.get("meta_description", ""),
            },
        }

        # Add tags if available
        tags = article.get("tags", [])
        if tags:
            payload["tags"] = await self._get_or_create_tags(tags)

        try:
            auth = aiohttp.BasicAuth(self.username, self.password)
            async with aiohttp.ClientSession(auth=auth) as session:
                async with session.post(endpoint, json=payload) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json()
                        url = data.get("link", "")
                        logger.info(f"Published to WordPress: {url}")
                        return url
                    else:
                        error = await resp.text()
                        logger.error(f"WordPress publish failed ({resp.status}): {error[:200]}")
                        return None
        except Exception as e:
            logger.error(f"WordPress publish error: {e}")
            return None

    async def _get_or_create_tags(self, tag_names: list) -> list:
        """Get or create WordPress tags, return list of tag IDs."""
        tag_ids = []
        auth = aiohttp.BasicAuth(self.username, self.password)

        async with aiohttp.ClientSession(auth=auth) as session:
            for name in tag_names[:10]:  # Limit tags
                # Try to find existing tag
                search_url = f"{self.url}/wp-json/wp/v2/tags?search={name}"
                try:
                    async with session.get(search_url) as resp:
                        if resp.status == 200:
                            tags = await resp.json()
                            if tags:
                                tag_ids.append(tags[0]["id"])
                                continue

                    # Create new tag
                    create_url = f"{self.url}/wp-json/wp/v2/tags"
                    async with session.post(create_url, json={"name": name}) as resp:
                        if resp.status in (200, 201):
                            tag = await resp.json()
                            tag_ids.append(tag["id"])
                except Exception:
                    pass

        return tag_ids


class BloggerPublisher:
    """Publish articles to Blogger/Blogspot via OAuth2 or Service Account."""

    def __init__(self):
        self.blog_id = settings.blogger.blog_id
        self.sa_json_path = settings.blogger.service_account_json
        self.base_url = "https://www.googleapis.com/blogger/v3"

        # Check for OAuth2 token file first (preferred), then service account
        from shared.config import BASE_DIR
        self.token_file = BASE_DIR / "data" / "blogger_token.json"
        self.has_oauth = self.token_file.exists()
        self.has_sa = bool(self.sa_json_path)

        self.enabled = bool(self.blog_id and (self.has_oauth or self.has_sa))
        if not self.enabled:
            logger.debug("Blogger publishing disabled (no blog ID or credentials)")

    def _get_access_token(self) -> Optional[str]:
        """Get access token — try OAuth2 refresh token first, then Service Account."""
        # Method 1: OAuth2 refresh token (from setup_blogger_auth.py)
        if self.has_oauth:
            try:
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request

                creds = Credentials.from_authorized_user_file(
                    str(self.token_file),
                    ['https://www.googleapis.com/auth/blogger']
                )
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    # Save refreshed token
                    import json
                    token_data = {
                        "token": creds.token,
                        "refresh_token": creds.refresh_token,
                        "token_uri": creds.token_uri,
                        "client_id": creds.client_id,
                        "client_secret": creds.client_secret,
                        "scopes": list(creds.scopes or []),
                    }
                    with open(self.token_file, "w") as f:
                        json.dump(token_data, f, indent=2, default=str)
                if creds.valid:
                    logger.debug("Using OAuth2 token for Blogger")
                    return creds.token
            except Exception as e:
                logger.warning(f"OAuth2 token failed, trying service account: {e}")

        # Method 2: Service Account
        if self.has_sa:
            try:
                from google.oauth2 import service_account
                from google.auth.transport.requests import Request

                sa_path = Path(self.sa_json_path)
                if not sa_path.is_absolute():
                    from shared.config import BASE_DIR
                    sa_path = BASE_DIR / sa_path

                if not sa_path.exists():
                    logger.error(f"Service account JSON not found: {sa_path}")
                    return None

                SCOPES = ['https://www.googleapis.com/auth/blogger']
                creds = service_account.Credentials.from_service_account_file(
                    str(sa_path), scopes=SCOPES
                )
                creds.refresh(Request())
                logger.debug("Using service account token for Blogger")
                return creds.token
            except Exception as e:
                logger.error(f"Service account token failed: {e}")
                return None

        return None

    async def publish(self, article: Dict, access_token: str = "") -> Optional[str]:
        """Publish an article to Blogger. Returns the post URL."""
        if not self.enabled:
            logger.debug("Blogger publishing disabled (no blog ID or service account)")
            return None

        if not access_token:
            access_token = self._get_access_token()
            if not access_token:
                logger.error("Could not obtain Blogger access token")
                return None

        content_html = markdown_to_html(article.get("content", ""))

        payload = {
            "kind": "blogger#post",
            "blog": {"id": self.blog_id},
            "title": article.get("title", "Untitled"),
            "content": content_html,
            "labels": article.get("tags", [])[:20],
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                url = f"{self.base_url}/blogs/{self.blog_id}/posts"
                async with session.post(url, json=payload) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json()
                        post_url = data.get("url", "")
                        logger.info(f"Published to Blogger: {post_url}")
                        return post_url
                    else:
                        error = await resp.text()
                        logger.error(f"Blogger publish failed ({resp.status}): {error[:200]}")
                        return None
        except Exception as e:
            logger.error(f"Blogger publish error: {e}")
            return None


def markdown_to_html(md_text: str) -> str:
    """Basic markdown to HTML conversion."""
    try:
        import markdown
        return markdown.markdown(
            md_text,
            extensions=["tables", "fenced_code", "toc", "nl2br"]
        )
    except ImportError:
        # Very basic fallback
        html = md_text
        # Headers
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        # Bold
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        # Links
        html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
        # Paragraphs
        html = re.sub(r'\n\n', '</p><p>', html)
        html = f'<p>{html}</p>'
        return html


class MultiPublisher:
    """Publish to all configured platforms."""

    def __init__(self):
        self.wordpress = WordPressPublisher()
        self.blogger = BloggerPublisher()

    async def publish_all(self, article: Dict) -> Dict[str, Optional[str]]:
        """Publish article to all enabled platforms. Returns dict of platform: url."""
        results = {}

        if self.wordpress.enabled:
            results["wordpress"] = await self.wordpress.publish(article)

        if self.blogger.enabled:
            results["blogger"] = await self.blogger.publish(article)

        # Log results
        published = {k: v for k, v in results.items() if v}
        if published:
            logger.info(f"Published to {len(published)} platforms: {list(published.keys())}")
        else:
            logger.warning("Article was not published to any platform")

        return results


# Singleton
publisher = MultiPublisher()
