"""
Central configuration for AI Money Machine.
Loads from .env using python-dotenv.
"""

import os
from pathlib import Path
from typing import List
from dotenv import dotenv_values

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

_env = dotenv_values(ENV_FILE)


def _e(key: str, default: str = "") -> str:
    """Get env value: os.environ first (CI/CD), then .env file, then default."""
    return os.environ.get(key, _env.get(key, default))


class GeminiSettings:
    api_key: str = _e("GEMINI_API_KEY")
    model_name: str = "gemini-2.5-flash"
    max_output_tokens: int = 8192
    temperature: float = 0.8
    rpm_limit: int = 15


class GroqSettings:
    api_key: str = _e("GROQ_API_KEY")
    model_name: str = "llama-3.3-70b-versatile"
    fallback_model: str = "llama-3.1-8b-instant"
    base_url: str = "https://api.groq.com/openai/v1"
    max_tokens: int = 8192
    rpm_limit: int = 30


class GitHubModelsSettings:
    api_key: str = _e("GITHUB_MODELS_PAT")
    model_name: str = "gpt-4.1"
    fallback_model: str = "gpt-4.1-mini"
    base_url: str = "https://models.inference.ai.azure.com"
    max_tokens: int = 4000
    rpm_limit: int = 15


class OpenRouterSettings:
    api_key: str = _e("OPENROUTER_API_KEY")
    model_name: str = "nvidia/nemotron-3-nano-30b-a3b:free"
    fallback_model: str = "arcee-ai/trinity-mini:free"
    base_url: str = "https://openrouter.ai/api/v1"
    max_tokens: int = 8192


class WordPressSettings:
    url: str = _e("WP_URL")
    username: str = _e("WP_USERNAME")
    password: str = _e("WP_PASSWORD")


class BloggerSettings:
    blog_id: str = _e("BLOGGER_BLOG_ID")
    service_account_json: str = _e("GOOGLE_SERVICE_ACCOUNT_JSON")


class AffiliateSettings:
    amazon_tag: str = _e("AMAZON_AFFILIATE_TAG")
    tokopedia_id: str = _e("TOKOPEDIA_AFFILIATE_ID")
    shopee_id: str = _e("SHOPEE_AFFILIATE_ID")
    alfagift_id: str = _e("ALFAGIFT_AFFILIATE_ID")


class PexelsSettings:
    api_key: str = _e("PEXELS_API_KEY")


class TelegramSettings:
    bot_token: str = _e("TELEGRAM_BOT_TOKEN")
    chat_id: str = _e("TELEGRAM_CHAT_ID")


class NewsSettings:
    site_url: str = _e("NEWS_SITE_URL")  # e.g. https://cikalnews.onrender.com


class SaaSSettings:
    host: str = _e("SAAS_HOST", "0.0.0.0")
    port: int = int(_e("SAAS_PORT", "8000"))
    secret_key: str = _e("SAAS_SECRET_KEY", "change-me")
    # Midtrans Payment Gateway (QRIS, GoPay, ShopeePay, Dana, OVO)
    midtrans_server_key: str = _e("MIDTRANS_SERVER_KEY")
    midtrans_client_key: str = _e("MIDTRANS_CLIENT_KEY")
    midtrans_is_production: bool = _e("MIDTRANS_IS_PRODUCTION", "false").lower() == "true"
    pro_price: int = int(_e("PRO_PRICE", "49900"))  # Rp 49.900/bulan


class Settings:
    gemini = GeminiSettings()
    groq = GroqSettings()
    github_models = GitHubModelsSettings()
    openrouter = OpenRouterSettings()
    wordpress = WordPressSettings()
    blogger = BloggerSettings()
    affiliate = AffiliateSettings()
    pexels = PexelsSettings()
    telegram = TelegramSettings()
    news = NewsSettings()
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
                  self.output_dir / "social"]:
            d.mkdir(parents=True, exist_ok=True)


# Singleton
settings = Settings()
settings.ensure_dirs()
