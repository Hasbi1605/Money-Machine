"""
Video Script Writer - Generates engaging video scripts using Gemini.
Supports both YouTube long-form and TikTok/Shorts format.
"""

import json
import random
from typing import Dict, List, Optional

from loguru import logger

from shared.gemini_client import gemini


# Proven niches for faceless YouTube channels
VIDEO_NICHES = {
    "en": [
        {"niche": "tech_reviews", "topics": [
            "best budget gadgets", "AI tools you need", "tech life hacks",
            "smartphone tips and tricks", "best free software",
            "future technology predictions", "gadgets under $50",
        ]},
        {"niche": "top_lists", "topics": [
            "most expensive things in the world", "unbelievable facts",
            "things you didn't know existed", "mind-blowing inventions",
            "craziest world records", "most luxurious hotels",
        ]},
        {"niche": "money_finance", "topics": [
            "passive income ideas", "money mistakes to avoid",
            "how billionaires think", "investment tips for beginners",
            "side hustle ideas", "financial habits of rich people",
        ]},
        {"niche": "productivity", "topics": [
            "morning routine of successful people", "productivity hacks",
            "apps that will change your life", "how to stop procrastinating",
            "study techniques backed by science", "minimalism tips",
        ]},
        {"niche": "ai_technology", "topics": [
            "AI tools that replace entire teams", "ChatGPT secrets",
            "how to use AI to make money", "AI vs humans",
            "future of artificial intelligence", "AI automation ideas",
        ]},
    ],
    "id": [
        {"niche": "teknologi", "topics": [
            "HP terbaik harga murah", "tips dan trik smartphone",
            "aplikasi gratis terbaik", "gadget murah berkualitas",
            "teknologi masa depan", "AI tools terbaik",
        ]},
        {"niche": "keuangan", "topics": [
            "cara menghasilkan uang dari HP", "investasi untuk pemula",
            "kesalahan keuangan yang harus dihindari", "bisnis modal kecil",
            "tips hemat ala orang kaya", "passive income Indonesia",
        ]},
        {"niche": "fakta_menarik", "topics": [
            "fakta mengejutkan yang jarang diketahui",
            "hal-hal termahal di dunia", "rekor dunia paling gila",
            "tempat paling berbahaya di dunia", "penemuan terbaru",
        ]},
        {"niche": "produktivitas", "topics": [
            "kebiasaan orang sukses", "tips produktif setiap hari",
            "cara belajar efektif", "aplikasi produktivitas terbaik",
        ]},
    ],
}


async def generate_video_script(
    language: str = "en",
    format_type: str = "youtube",  # "youtube" or "short"
    niche: Optional[str] = None,
    topic: Optional[str] = None,
) -> Dict:
    """
    Generate a video script with timing cues and visual suggestions.

    Args:
        language: 'en' or 'id'
        format_type: 'youtube' (8-12 min) or 'short' (30-60 sec)
        niche: specific niche or random
        topic: specific topic or random

    Returns:
        Dict with script, title, description, tags, scenes
    """

    # Select niche and topic if not provided
    niches = VIDEO_NICHES.get(language, VIDEO_NICHES["en"])

    if not niche:
        selected_niche = random.choice(niches)
        niche = selected_niche["niche"]
    else:
        selected_niche = next((n for n in niches if n["niche"] == niche), random.choice(niches))

    if not topic:
        topic = random.choice(selected_niche["topics"])

    lang_name = "Indonesian (Bahasa Indonesia)" if language == "id" else "English"

    if format_type == "short":
        duration_guide = "30-60 seconds (TikTok/YouTube Shorts format)"
        scene_count = "3-5"
        word_count = "80-150 words"
    else:
        duration_guide = "8-12 minutes (standard YouTube video)"
        scene_count = "12-20"
        word_count = "1200-1800 words"

    system_instruction = f"""You are a professional video scriptwriter for faceless YouTube/TikTok channels.
You write in {lang_name}.
Your scripts are engaging, well-paced, and optimized for viewer retention.
You include specific visual directions for each scene (what stock footage to show).
You write hooks that grab attention in the first 3 seconds."""

    prompt = f"""Write a complete video script about: "{topic}"

**Language:** {lang_name}
**Format:** {duration_guide}
**Niche:** {niche}

**Script Structure:**
1. HOOK (first 3 seconds): Shocking statement, question, or teaser
2. INTRO (10-15 seconds): Brief context, promise what viewers will learn
3. MAIN CONTENT: {scene_count} scenes, each with:
   - Narration text (what the AI voice will say)
   - Visual direction (what stock footage/images to show)
   - Estimated duration in seconds
4. CTA (Call to Action): Subscribe, like, comment prompt

**Requirements:**
- Write narration that sounds natural when read by text-to-speech
- Avoid complex words that TTS might mispronounce
- Include transition phrases between scenes
- Add engagement hooks (questions to viewers) every 2-3 scenes
- Total narration: {word_count}

**Return as JSON with these fields:**
- title: Click-worthy YouTube title (with keyword, max 70 chars)
- description: YouTube description with keywords (200-300 words), include relevant hashtags
- tags: Array of 10-15 relevant YouTube tags
- thumbnail_text: Short text overlay for thumbnail (max 5 words)
- scenes: Array of scene objects, each with:
  - scene_number: int
  - narration: string (what the voice says)
  - visual_query: string (search query for stock footage on Pexels)
  - duration_seconds: estimated duration
- total_duration_estimate: total estimated duration in seconds
- niche: "{niche}"
- topic: "{topic}"
"""

    logger.info(f"Generating {format_type} script: '{topic}' ({language})")

    try:
        result = await gemini.generate_json(prompt, system_instruction=system_instruction)

        # Validate
        if not result.get("scenes"):
            raise ValueError("No scenes in generated script")

        result["language"] = language
        result["format_type"] = format_type

        # Calculate full narration text
        full_narration = " ".join(
            scene.get("narration", "") for scene in result["scenes"]
        )
        result["full_narration"] = full_narration
        result["word_count"] = len(full_narration.split())

        logger.info(
            f"Script generated: '{result.get('title', '')}' "
            f"({len(result['scenes'])} scenes, ~{result['word_count']} words)"
        )

        return result

    except Exception as e:
        logger.error(f"Script generation failed: {e}")
        return {}


async def generate_shorts_script(language: str = "en") -> Dict:
    """Convenience function for generating YouTube Shorts / TikTok scripts."""
    return await generate_video_script(language=language, format_type="short")
