import asyncio
from news_app.social_generator import generate_carousel, generate_caption
from shared.database import get_news_articles
from shared.notifier import notifier

async def run_test():
    print("Fetching top 5 recent articles...")
    articles = await get_news_articles(limit=5)
    
    if not articles:
        print("No articles found in DB.")
        return

    print("Generating carousel images...")
    slides = await generate_carousel(articles)
    print(f"Generated {len(slides)} slides.")

    print("Generating caption...")
    caption = await generate_caption(articles)
    print("Caption snippet: ", caption[:100], "...")

    print("Sending via Telegram...")
    success = await notifier.send_media_group(slides, caption)
    if success:
        print("Successfully sent to Telegram!")
    else:
        print("Failed to send to Telegram.")

if __name__ == "__main__":
    asyncio.run(run_test())
