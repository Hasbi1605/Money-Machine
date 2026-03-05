"""
Video Engine Orchestrator - Runs the full video generation pipeline.
Script Generation → TTS → Stock Footage → Assembly → Upload → Notify
"""

import asyncio
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

from loguru import logger

from video_engine.script_writer import generate_video_script, generate_shorts_script
from video_engine.tts_engine import generate_full_audio
from video_engine.video_assembler import download_scene_footage, assemble_video_async
from video_engine.uploader import uploader
from shared.database import log_video, log_pipeline_run, finish_pipeline_run
from shared.notifier import notifier
from shared.config import settings


async def run_video_pipeline(
    language: str = "en",
    format_type: str = "youtube",
    upload: bool = True,
) -> bool:
    """
    Run the full video generation pipeline.

    Steps:
    1. Generate video script with Gemini
    2. Convert narration to speech with Edge TTS
    3. Download stock footage from Pexels
    4. Assemble video (footage + audio + subtitles)
    5. Upload to YouTube/TikTok
    6. Log and notify

    Returns True if successful.
    """
    pipeline_name = f"Video Engine ({language.upper()}, {format_type})"
    run_id = await log_pipeline_run(pipeline_name)

    # Create temp working directory
    work_dir = Path(tempfile.mkdtemp(prefix="video_"))

    try:
        # Step 1: Generate Script
        logger.info(f"[{pipeline_name}] Step 1: Generating script")

        if format_type == "short":
            script = await generate_shorts_script(language)
        else:
            script = await generate_video_script(language=language, format_type=format_type)

        if not script or not script.get("scenes"):
            raise Exception("Script generation failed")

        title = script.get("title", "Untitled Video")
        scenes = script.get("scenes", [])
        logger.info(f"[{pipeline_name}] Script ready: '{title}' ({len(scenes)} scenes)")

        # Save script
        script_path = work_dir / "script.json"
        import json
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)

        # Step 2: Generate TTS Audio
        logger.info(f"[{pipeline_name}] Step 2: Generating audio (TTS)")
        full_narration = script.get("full_narration", "")

        if not full_narration:
            full_narration = " ".join(s.get("narration", "") for s in scenes)

        audio_path = work_dir / "narration.mp3"
        audio_result = await generate_full_audio(
            full_text=full_narration,
            output_path=audio_path,
            language=language,
            gender="male",
        )

        if not audio_result:
            raise Exception("TTS audio generation failed")

        # Step 3: Download Stock Footage
        logger.info(f"[{pipeline_name}] Step 3: Downloading stock footage")
        footage_dir = work_dir / "footage"
        footage_paths = await download_scene_footage(scenes, footage_dir)

        # Step 4: Assemble Video
        logger.info(f"[{pipeline_name}] Step 4: Assembling video")

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        slug = title.lower().replace(" ", "_")[:30]
        output_filename = f"{slug}_{language}_{timestamp}.mp4"
        output_path = settings.output_dir / "videos" / output_filename

        video_path = await assemble_video_async(
            audio_path=audio_path,
            footage_paths=footage_paths,
            scenes=scenes,
            output_path=output_path,
            title=title,
        )

        if not video_path or not video_path.exists():
            raise Exception("Video assembly failed")

        video_size_mb = video_path.stat().st_size / (1024 * 1024)
        logger.info(f"[{pipeline_name}] Video ready: {video_size_mb:.1f} MB")

        # Step 5: Upload
        upload_results = {}
        if upload:
            logger.info(f"[{pipeline_name}] Step 5: Uploading")
            platforms = ["youtube"]
            if format_type == "short":
                platforms.append("tiktok")

            upload_results = await uploader.upload(
                video_path=video_path,
                metadata={
                    "title": title,
                    "description": script.get("description", ""),
                    "tags": script.get("tags", []),
                },
                platforms=platforms,
            )
        else:
            logger.info(f"[{pipeline_name}] Upload skipped (disabled)")

        # Step 6: Log & Notify
        uploaded_urls = {k: v for k, v in upload_results.items() if v}
        platform_list = ", ".join(uploaded_urls.keys()) if uploaded_urls else "local only"

        # Get approximate duration from audio
        try:
            from moviepy.editor import AudioFileClip
            audio_clip = AudioFileClip(str(audio_path))
            duration = audio_clip.duration
            audio_clip.close()
        except Exception:
            duration = script.get("total_duration_estimate", 0)

        for platform, url in uploaded_urls.items():
            await log_video(
                title=title,
                language=language,
                platform=platform,
                niche=script.get("niche", ""),
                duration_seconds=duration,
                platform_url=url or "",
            )

        if not uploaded_urls:
            await log_video(
                title=title,
                language=language,
                platform="local",
                niche=script.get("niche", ""),
                duration_seconds=duration,
                platform_url=str(video_path),
            )

        await finish_pipeline_run(run_id, items=1)
        await notifier.send_success(
            pipeline_name,
            f"🎬 <b>{title}</b>\n"
            f"⏱ Duration: {duration:.0f}s\n"
            f"📦 Size: {video_size_mb:.1f} MB\n"
            f"🌐 Uploaded: {platform_list}\n"
            f"📹 Scenes: {len(scenes)}"
        )

        logger.info(f"[{pipeline_name}] ✅ Pipeline completed successfully")
        return True

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{pipeline_name}] ❌ Pipeline failed: {error_msg}")
        await finish_pipeline_run(run_id, error=error_msg)
        await notifier.send_error(pipeline_name, error_msg)
        return False

    finally:
        # Cleanup temp directory (keep final video in output/)
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass


async def run_video_cycle():
    """Run one full cycle of video generation for all languages."""
    languages = settings.get_languages()
    logger.info(f"Starting video cycle for languages: {languages}")

    results = {}
    for lang in languages:
        # Generate full YouTube video
        success = await run_video_pipeline(lang, "youtube")
        results[f"{lang}_youtube"] = success

        await asyncio.sleep(10)  # Delay between generations

    success_count = sum(1 for v in results.values() if v)
    total = len(results)
    logger.info(f"Video cycle completed: {success_count}/{total} successful")

    return results


if __name__ == "__main__":
    asyncio.run(run_video_cycle())
