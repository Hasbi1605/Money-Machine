"""
Logging setup using loguru.
"""

import sys
from loguru import logger
from shared.config import settings


def setup_logging():
    """Configure logging for the application."""
    logger.remove()  # Remove default handler

    # Console output
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    )

    # File output - rotate daily
    logger.add(
        settings.logs_dir / "ai_money_machine_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
    )

    # Error-specific log
    logger.add(
        settings.logs_dir / "errors.log",
        rotation="1 week",
        retention="30 days",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}\n{exception}",
    )

    return logger


setup_logging()
