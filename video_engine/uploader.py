"""
Video Uploader - Auto-uploads videos to YouTube using YouTube Data API v3.
Handles OAuth2 authentication and video metadata.
"""

import asyncio
import json
import os
import pickle
from pathlib import Path
from typing import Optional, Dict

from loguru import logger

from shared.config import settings


CREDENTIALS_DIR = settings.data_dir / "credentials"
YOUTUBE_TOKEN_PATH = CREDENTIALS_DIR / "youtube_token.pickle"
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_youtube_service():
    """Get authenticated YouTube API service."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        logger.error("Google API libraries not installed")
        return None

    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    creds = None

    # Load existing token
    if YOUTUBE_TOKEN_PATH.exists():
        with open(YOUTUBE_TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            logger.warning(f"Token refresh failed: {e}")
            creds = None

    # If no valid creds, need to authenticate
    if not creds or not creds.valid:
        client_id = settings.youtube.client_id
        client_secret = settings.youtube.client_secret

        if not client_id or not client_secret:
            logger.error("YouTube client ID/secret not configured")
            return None

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }

        flow = InstalledAppFlow.from_client_config(client_config, YOUTUBE_SCOPES)
        creds = flow.run_local_server(port=0)

        # Save token for next run
        with open(YOUTUBE_TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)
        logger.info("YouTube credentials saved")

    return build("youtube", "v3", credentials=creds)


async def upload_to_youtube(
    video_path: Path,
    title: str,
    description: str,
    tags: list,
    category_id: str = "28",  # Science & Technology
    privacy: str = "public",
    thumbnail_path: Optional[Path] = None,
) -> Optional[str]:
    """
    Upload a video to YouTube.

    Args:
        video_path: Path to the video file
        title: Video title
        description: Video description
        tags: List of tags
        category_id: YouTube category ID (28 = Science & Technology)
        privacy: 'public', 'private', or 'unlisted'
        thumbnail_path: Optional custom thumbnail

    Returns:
        YouTube video URL if successful, None otherwise
    """

    def _upload():
        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError:
            logger.error("Google API client library not installed")
            return None

        youtube = get_youtube_service()
        if not youtube:
            return None

        body = {
            "snippet": {
                "title": title[:100],  # YouTube limit
                "description": description[:5000],
                "tags": tags[:500],  # YouTube limit
                "categoryId": category_id,
                "defaultLanguage": "en",
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024,  # 1MB chunks
        )

        try:
            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.debug(f"Upload progress: {progress}%")

            video_id = response.get("id", "")
            video_url = f"https://youtu.be/{video_id}"
            logger.info(f"Uploaded to YouTube: {video_url}")

            # Set thumbnail if provided
            if thumbnail_path and thumbnail_path.exists() and video_id:
                try:
                    youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=MediaFileUpload(str(thumbnail_path)),
                    ).execute()
                    logger.info("Custom thumbnail set")
                except Exception as e:
                    logger.warning(f"Thumbnail upload failed: {e}")

            return video_url

        except Exception as e:
            logger.error(f"YouTube upload failed: {e}")
            return None

    # Run in thread pool since it's blocking I/O
    return await asyncio.to_thread(_upload)


async def upload_to_tiktok(
    video_path: Path,
    description: str,
    tags: list,
) -> Optional[str]:
    """
    Upload to TikTok.
    Note: TikTok's official API for video upload is limited.
    This is a placeholder — for production, consider using
    TikTok's Content Posting API or a service like SocialBee.
    """
    logger.info(f"TikTok upload placeholder for: {video_path}")
    logger.warning(
        "TikTok auto-upload requires additional setup. "
        "Consider using TikTok Content Posting API or manual upload. "
        "Video is saved locally for manual upload."
    )
    return None


class VideoUploader:
    """Unified video uploader for multiple platforms."""

    async def upload(
        self,
        video_path: Path,
        metadata: Dict,
        platforms: list = None,
    ) -> Dict[str, Optional[str]]:
        """Upload video to specified platforms."""
        if platforms is None:
            platforms = ["youtube"]

        results = {}

        title = metadata.get("title", "Untitled Video")
        description = metadata.get("description", "")
        tags = metadata.get("tags", [])

        for platform in platforms:
            if platform == "youtube":
                url = await upload_to_youtube(
                    video_path=video_path,
                    title=title,
                    description=description,
                    tags=tags,
                    thumbnail_path=metadata.get("thumbnail_path"),
                )
                results["youtube"] = url

            elif platform == "tiktok":
                url = await upload_to_tiktok(
                    video_path=video_path,
                    description=f"{title} {' '.join(f'#{t}' for t in tags[:5])}",
                    tags=tags,
                )
                results["tiktok"] = url

        return results


# Singleton
uploader = VideoUploader()
