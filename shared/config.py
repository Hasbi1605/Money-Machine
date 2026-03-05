"""
Central configuration for AI Money Machine.
Loads from .env and provides typed settings.
"""

from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


BASE_DIR = Path(__file__).resolve().parent.parent


class GeminiSettings(BaseSettings):
    api_key: str = Field(default="", alias="GEMINI_API_KEY")
    model_name: str = "gemini-2.0-flash"
    max_output_tokens: int = 8192
    temperature: float = 0.8
    rpm_limit: int = 15  # free tier: 15 requests per minute


class WordPressSettings(BaseSettings):
    url: str = Field(default="", alias="WP_URL")
    username: str = Field(default="", alias="WP_USERNAME")
    password: str = Field(default="", alias="WP_PASSWORD")


class MediumSettings(BaseSettings):
    token: str = Field(default="", alias="MEDIUM_TOKEN")


class BloggerSettings(BaseSettings):
    blog_id: str = Field(default="", alias="BLOGGER_BLOG_ID")
    service_account_json: str = Field(default="", alias="GOOGLE_SERVICE_ACCOUNT_JSON")


class AffiliateSettings(BaseSettings):
    amazon_tag: str = Field(default="", alias="AMAZON_AFFILIATE_TAG")
    tokopedia_id: str = Field(default="", alias="TOKOPEDIA_AFFILIATE_ID")
    shopee_id: str = Field(default="", alias="SHOPEE_AFFILIATE_ID")


class YouTubeSettings(BaseSettings):
    client_id: str = Field(default="", alias="YOUTUBE_CLIENT_ID")
    client_secret: str = Field(default="", alias="YOUTUBE_CLIENT_SECRET")


class PexelsSettings(BaseSettings):
    api_key: str = Field(default="", alias="PEXELS_API_KEY")


class TelegramSettings(BaseSettings):
    bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")


class SaaSSettings(BaseSettings):
    host: str = Field(default="0.0.0.0", alias="SAAS_HOST")
    port: int = Field(default=8000, alias="SAAS_PORT")
    secret_key: str = Field(default="change-me", alias="SAAS_SECRET_KEY")
    lemonsqueezy_api_key: str = Field(default="", alias="LEMONSQUEEZY_API_KEY")
    lemonsqueezy_webhook_secret: str = Field(default="", alias="LEMONSQUEEZY_WEBHOOK_SECRET")


class Settings(BaseSettings):
    gemini: GeminiSettings = GeminiSettings()
    wordpress: WordPressSettings = WordPressSettings()
    medium: MediumSettings = MediumSettings()
    blogger: BloggerSettings = BloggerSettings()
    affiliate: AffiliateSettings = AffiliateSettings()
    youtube: YouTubeSettings = YouTubeSettings()
    pexels: PexelsSettings = PexelsSettings()
    telegram: TelegramSettings = TelegramSettings()
    saas: SaaSSettings = SaaSSettings()

    content_languages: str = Field(default="en,id", alias="CONTENT_LANGUAGES")
    timezone: str = Field(default="Asia/Jakarta", alias="TIMEZONE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Directories
    output_dir: Path = BASE_DIR / "output"
    logs_dir: Path = BASE_DIR / "logs"
    data_dir: Path = BASE_DIR / "data"

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"

    def get_languages(self) -> List[str]:
        return [lang.strip() for lang in self.content_languages.split(",")]

    def ensure_dirs(self):
        """Create required directories."""
        for d in [self.output_dir, self.logs_dir, self.data_dir,
                  self.output_dir / "articles",
                  self.output_dir / "videos",
                  self.output_dir / "thumbnails"]:
            d.mkdir(parents=True, exist_ok=True)


# Singleton
settings = Settings()
settings.ensure_dirs()
