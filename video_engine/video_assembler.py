"""
Video Assembler - Combines TTS audio + stock footage + subtitles into final video.
Uses MoviePy for video editing and Pexels API for free stock footage.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import aiohttp
from loguru import logger

from shared.config import settings


async def search_pexels_video(
    query: str,
    min_duration: int = 5,
    max_duration: int = 30,
) -> Optional[str]:
    """
    Search for a stock video on Pexels and return download URL.

    Args:
        query: Search query
        min_duration: Minimum video duration
        max_duration: Maximum video duration

    Returns:
        URL of the video file, or None
    """
    api_key = settings.pexels.api_key
    if not api_key:
        logger.warning("Pexels API key not set, cannot download stock footage")
        return None

    headers = {"Authorization": api_key}
    url = "https://api.pexels.com/videos/search"
    params = {
        "query": query,
        "per_page": 10,
        "size": "medium",
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.error(f"Pexels API error: {resp.status}")
                    return None

                data = await resp.json()
                videos = data.get("videos", [])

                # Filter by duration
                suitable = [
                    v for v in videos
                    if min_duration <= v.get("duration", 0) <= max_duration
                ]

                if not suitable:
                    suitable = videos  # Fall back to any result

                if not suitable:
                    logger.warning(f"No Pexels videos found for '{query}'")
                    return None

                # Pick a random suitable video
                import random
                video = random.choice(suitable)

                # Get the HD or SD file
                files = video.get("video_files", [])
                # Prefer HD quality
                hd_files = [f for f in files if f.get("quality") == "hd"]
                sd_files = [f for f in files if f.get("quality") == "sd"]

                chosen = (hd_files or sd_files or files)[0] if files else None
                if chosen:
                    return chosen.get("link")

    except Exception as e:
        logger.error(f"Pexels search failed: {e}")

    return None


async def download_video(url: str, output_path: Path) -> Optional[Path]:
    """Download a video from URL."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            f.write(chunk)
                    logger.debug(f"Downloaded video to {output_path}")
                    return output_path
    except Exception as e:
        logger.error(f"Video download failed: {e}")
    return None


async def download_scene_footage(
    scenes: List[Dict],
    output_dir: Path,
) -> List[Optional[Path]]:
    """Download stock footage for each scene."""
    output_dir.mkdir(parents=True, exist_ok=True)
    footage_paths = []

    for i, scene in enumerate(scenes):
        query = scene.get("visual_query", "abstract background")
        video_url = await search_pexels_video(query)

        if video_url:
            path = output_dir / f"footage_{i+1:03d}.mp4"
            result = await download_video(video_url, path)
            footage_paths.append(result)
        else:
            footage_paths.append(None)

        await asyncio.sleep(0.5)  # Rate limit

    valid = sum(1 for f in footage_paths if f)
    logger.info(f"Downloaded {valid}/{len(scenes)} stock footage clips")
    return footage_paths


def assemble_video(
    audio_path: Path,
    footage_paths: List[Optional[Path]],
    scenes: List[Dict],
    output_path: Path,
    title: str = "",
    resolution: Tuple[int, int] = (1920, 1080),
) -> Optional[Path]:
    """
    Assemble final video from audio + stock footage + subtitles.

    This is the CPU-intensive part — runs synchronously.
    """
    try:
        from moviepy.editor import (
            VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip,
            ColorClip, concatenate_videoclips, CompositeAudioClip
        )
    except ImportError:
        logger.error("moviepy not installed. Run: pip install moviepy")
        return None

    logger.info(f"Assembling video: '{title}'")

    try:
        # Load the full audio
        audio = AudioFileClip(str(audio_path))
        total_duration = audio.duration

        # Calculate duration per scene
        num_scenes = len(scenes)
        scene_durations = []
        for scene in scenes:
            d = scene.get("duration_seconds", total_duration / num_scenes)
            scene_durations.append(d)

        # Normalize durations to match audio
        total_est = sum(scene_durations)
        if total_est > 0:
            scale = total_duration / total_est
            scene_durations = [d * scale for d in scene_durations]

        # Create video clips for each scene
        clips = []
        current_time = 0

        for i, (footage_path, scene, duration) in enumerate(
            zip(footage_paths, scenes, scene_durations)
        ):
            if footage_path and footage_path.exists():
                try:
                    clip = VideoFileClip(str(footage_path))
                    # Resize to target resolution
                    clip = clip.resize(resolution)

                    # Loop or trim to match scene duration
                    if clip.duration < duration:
                        # Loop the clip
                        loops = int(duration / clip.duration) + 1
                        clip = concatenate_videoclips([clip] * loops)

                    clip = clip.subclip(0, duration)
                except Exception as e:
                    logger.warning(f"Failed to load footage for scene {i+1}: {e}")
                    clip = ColorClip(
                        size=resolution,
                        color=(20, 20, 30),
                        duration=duration,
                    )
            else:
                # Fallback: solid color background
                clip = ColorClip(
                    size=resolution,
                    color=(20, 20, 30),
                    duration=duration,
                )

            # Add subtitle for this scene
            narration = scene.get("narration", "")
            if narration:
                try:
                    # Split narration into shorter lines for readability
                    words = narration.split()
                    lines = []
                    current_line = []
                    for word in words:
                        current_line.append(word)
                        if len(" ".join(current_line)) > 50:
                            lines.append(" ".join(current_line))
                            current_line = []
                    if current_line:
                        lines.append(" ".join(current_line))

                    subtitle_text = "\n".join(lines[:3])  # Max 3 lines

                    txt_clip = TextClip(
                        subtitle_text,
                        fontsize=36,
                        color="white",
                        font="Arial-Bold",
                        stroke_color="black",
                        stroke_width=2,
                        size=(resolution[0] - 100, None),
                        method="caption",
                    ).set_duration(duration).set_position(("center", "bottom"), relative=False).set_position(("center", resolution[1] - 150))

                    clip = CompositeVideoClip([clip, txt_clip])
                except Exception as e:
                    logger.warning(f"Subtitle creation failed for scene {i+1}: {e}")

            clips.append(clip)
            current_time += duration

        # Concatenate all scene clips
        if not clips:
            logger.error("No clips to assemble")
            return None

        final_video = concatenate_videoclips(clips, method="compose")

        # Add audio
        final_video = final_video.set_audio(audio)

        # Write output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        final_video.write_videofile(
            str(output_path),
            fps=24,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=2,
            logger=None,  # Suppress moviepy's verbose output
        )

        # Cleanup
        audio.close()
        final_video.close()
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass

        if output_path.exists():
            size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.info(f"Video assembled: {output_path} ({size_mb:.1f} MB)")
            return output_path

    except Exception as e:
        logger.error(f"Video assembly failed: {e}")

    return None


async def assemble_video_async(
    audio_path: Path,
    footage_paths: List[Optional[Path]],
    scenes: List[Dict],
    output_path: Path,
    title: str = "",
) -> Optional[Path]:
    """Async wrapper for video assembly (runs in thread pool)."""
    return await asyncio.to_thread(
        assemble_video,
        audio_path,
        footage_paths,
        scenes,
        output_path,
        title,
    )
