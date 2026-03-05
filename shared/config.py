"""
Central configuration for AI Money Machine.
Loads from .env using python-dotenv.
"""

from pathlib import Path
from typing import List
from dotenv import dotenv_values

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

_env = dotenv_values(ENV_FILE)


def _e(key: str, default: str = "") -> str:
    """Get env value with fallback."""
    return _env.get(key, default)


class GeminiSettings:
    api_key: str = _e("GEMINI_API_KEY")
    model_name: str = "gemini-2.5-flash"
    max_output_tokens: int = 8192
    temperature: float = 0.8
    rpm_limit: int = 15


class WordPressSettings:
    url: str = _e("WP_URL")
    username: str = _e("WP_USERNAME")
    password: str = _e("WP_PASSWORD")


class MediumSettings:
    token: str = _e("MEDIUM_TOKEN")


class BloggerSettings:
    blog_id: str = _e("BLOGGER_BLOG_ID")
    service_account_json: str = _e("GOOGLE_SERVICE_ACCOUNT_JSON")


class AffiliateSettings:
    amazon_tag: str = _e("AMAZON_AFFILIATE_TAG")
    tokopedia_id: str = _e("TOKOPEDIA_AFFILIATE_ID")
    shopee_id: str = _e("SHOPEE_AFFILIATE_ID")


class YouTubeSettings:
    client_id: str = _e("YOUTUBE_CLIENT_ID")
    client_secret: str = _e("YOUTUBE_CLIENT_SECRET")


class PexelsSettings:
    api_key: str = _e("PEXELS_API_KEY")


class TelegramSettings:
    bot_token: str = _e("TELEGRAM_BOT_TOKEN")
    chat_id: str = _e("TELEGRAM_CHAT_ID")


class SaaSSettings:
    host: str = _e("SAAS_HOST", "0.0.0.0")
    port: int = int(_e("SAAS_PORT", "8000"))
    secret_key: str = _e("SAAS_SECRET_KEY", "change-me")
    lemonsqueezy_api_key: str = _e("LEMONSQUEEZY_API_KEY")
    lemonsqueezy_webhook_secret: str = _e("LEMONSQUEEZY_WEBHOOK_SECRET")


class Settings:
    gemini = GeminiSettings()
    wordpress = WordPressSettings()
    medium = MediumSettings()
    blogger = BloggerSettings()
    affiliate = AffiliateSettings()
    youtube = YouTubeSettings()
    pexels = PexelsSettings()
    telegram = TelegramSettings()
    saas = SaaSSettings()

    content_languages: str = _e("CONTENT_LANGUAGES", "en,id")
    timezone: str = _e("TIMEZONE", "Asia/Jakarta")
    log_level: str = _e("LOG_LEVEL", "INFO")

    output_dir: Path = BASE_DIR / "output"
    logs_dir: Path = BASE_DIR / "logs"
    data_dir: Path = BASE_DIR / "data"

    def get_languages(self) -> List[str]:
        return [lang.strip() for lang in self.content_languages.split(",")]

    def ensure_dirs(self):
        for d in [self.output_dir, self.logs_dir, self.data_dir,
                  self.output_dir / "articles",
                  self.output_dir / "videos",
                  self.output_dir / "thumbnails"]:
            d.mkdir(parents=True, exist_ok=True)


# Singleton
settings = Settings()
settings.ensure_dirs()
