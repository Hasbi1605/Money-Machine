"""
TTS Engine - Text-to-Speech using Edge-TTS (free, high quality).
Converts video script narration to audio files.
"""

import asyncio
import os
from pathlib import Path
from typing import Optional

import edge_tts
from loguru import logger

from shared.config import settings


# Voice options per language
VOICES = {
    "en": {
        "male": "en-US-GuyNeural",
        "female": "en-US-JennyNeural",
        "alt_male": "en-US-ChristopherNeural",
        "alt_female": "en-US-AriaNeural",
    },
    "id": {
        "male": "id-ID-ArdiNeural",
        "female": "id-ID-GadisNeural",
    },
}

# Rate and pitch adjustments for more engaging narration
SPEECH_RATE = "+10%"  # Slightly faster for YouTube content
SPEECH_PITCH = "+0Hz"  # Normal pitch


async def text_to_speech(
    text: str,
    output_path: Path,
    language: str = "en",
    gender: str = "male",
    rate: str = SPEECH_RATE,
    pitch: str = SPEECH_PITCH,
) -> Optional[Path]:
    """
    Convert text to speech using Edge TTS.

    Args:
        text: The text to convert
        output_path: Where to save the audio file (.mp3)
        language: Language code ('en' or 'id')
        gender: 'male' or 'female'
        rate: Speech rate adjustment (e.g., '+10%', '-5%')
        pitch: Pitch adjustment (e.g., '+5Hz', '-3Hz')

    Returns:
        Path to the saved audio file, or None on failure
    """
    voices = VOICES.get(language, VOICES["en"])
    voice = voices.get(gender, voices.get("male", "en-US-GuyNeural"))

    logger.info(f"TTS: Converting {len(text)} chars with voice '{voice}'")

    try:
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            pitch=pitch,
        )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        await communicate.save(str(output_path))

        if output_path.exists() and output_path.stat().st_size > 0:
            size_kb = output_path.stat().st_size / 1024
            logger.info(f"TTS: Saved audio to {output_path} ({size_kb:.1f} KB)")
            return output_path
        else:
            logger.error("TTS: Output file is empty or missing")
            return None

    except Exception as e:
        logger.error(f"TTS failed: {e}")
        return None


async def generate_scene_audio(
    scenes: list,
    output_dir: Path,
    language: str = "en",
    gender: str = "male",
) -> list:
    """
    Generate individual audio files for each scene.

    Args:
        scenes: List of scene dicts with 'narration' field
        output_dir: Directory to save audio files
        language: Language code
        gender: Voice gender

    Returns:
        List of paths to generated audio files (in scene order)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    audio_files = []

    for i, scene in enumerate(scenes):
        narration = scene.get("narration", "")
        if not narration.strip():
            logger.warning(f"Scene {i+1} has empty narration, skipping")
            audio_files.append(None)
            continue

        output_path = output_dir / f"scene_{i+1:03d}.mp3"
        result = await text_to_speech(
            text=narration,
            output_path=output_path,
            language=language,
            gender=gender,
        )
        audio_files.append(result)

        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)

    valid = sum(1 for f in audio_files if f)
    logger.info(f"Generated {valid}/{len(scenes)} scene audio files")

    return audio_files


async def generate_full_audio(
    full_text: str,
    output_path: Path,
    language: str = "en",
    gender: str = "male",
) -> Optional[Path]:
    """Generate a single audio file from full narration text."""
    return await text_to_speech(
        text=full_text,
        output_path=output_path,
        language=language,
        gender=gender,
    )
