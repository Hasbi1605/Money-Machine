"""
Micro-SaaS App - AI-powered writing tools.
FastAPI backend with 3 tools:
1. AI Resume/CV Writer
2. AI Caption Generator (30 social media captions at once)
3. AI Email Writer
"""

import asyncio
import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger
from pydantic import BaseModel

from shared.gemini_client import gemini
from shared.config import settings

# ---------------------
# App Setup
# ---------------------

app = FastAPI(
    title="AI Writing Tools",
    description="Free AI-powered writing tools",
    version="1.0.0",
)

SAAS_DIR = Path(__file__).parent
TEMPLATES_DIR = SAAS_DIR / "templates"
STATIC_DIR = SAAS_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Mount static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ---------------------
# Rate Limiting (Simple in-memory)
# ---------------------

FREE_USES_PER_DAY = 3
usage_tracker: dict = {}  # IP -> {"date": date, "count": int}


def check_rate_limit(ip: str) -> tuple[bool, int]:
    """Check if an IP has remaining free uses. Returns (allowed, remaining)."""
    today = date.today().isoformat()

    if ip not in usage_tracker or usage_tracker[ip]["date"] != today:
        usage_tracker[ip] = {"date": today, "count": 0}

    count = usage_tracker[ip]["count"]
    remaining = FREE_USES_PER_DAY - count

    if remaining <= 0:
        return False, 0

    return True, remaining


def increment_usage(ip: str):
    """Increment usage counter for an IP."""
    today = date.today().isoformat()
    if ip not in usage_tracker or usage_tracker[ip]["date"] != today:
        usage_tracker[ip] = {"date": today, "count": 0}
    usage_tracker[ip]["count"] += 1


# ---------------------
# Request Models
# ---------------------

class ResumeRequest(BaseModel):
    name: str
    title: str  # Job title / position
    experience: str  # Work experience summary
    skills: str  # Comma-separated skills
    education: str  # Education background
    language: str = "en"


class CaptionRequest(BaseModel):
    topic: str
    platform: str = "instagram"  # instagram, twitter, linkedin, tiktok
    tone: str = "professional"  # professional, casual, funny, motivational
    count: int = 10
    language: str = "en"


class EmailRequest(BaseModel):
    purpose: str  # e.g., "job application", "follow up", "complaint"
    context: str  # Additional context
    tone: str = "professional"
    language: str = "en"


# ---------------------
# Routes - Pages
# ---------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/resume", response_class=HTMLResponse)
async def resume_page(request: Request):
    return templates.TemplateResponse("resume.html", {"request": request})


@app.get("/captions", response_class=HTMLResponse)
async def captions_page(request: Request):
    return templates.TemplateResponse("captions.html", {"request": request})


@app.get("/email", response_class=HTMLResponse)
async def email_page(request: Request):
    return templates.TemplateResponse("email.html", {"request": request})


# ---------------------
# Routes - API
# ---------------------

@app.post("/api/resume")
async def generate_resume(request: Request, data: ResumeRequest):
    ip = request.client.host
    allowed, remaining = check_rate_limit(ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Daily free limit reached. Upgrade to Pro for unlimited access!"
        )

    lang = "Indonesian" if data.language == "id" else "English"

    prompt = f"""Create a professional resume/CV based on this information:

Name: {data.name}
Target Position: {data.title}
Work Experience: {data.experience}
Skills: {data.skills}
Education: {data.education}
Language: {lang}

Generate a complete, ATS-friendly resume with:
1. Professional summary (2-3 sentences)
2. Work experience (formatted with bullet points, action verbs, quantified achievements)
3. Skills section (categorized: Technical, Soft Skills)
4. Education section
5. Key achievements/certifications if relevant

Return as JSON with fields:
- summary: professional summary paragraph
- experience: array of job objects (title, company, period, bullets: [])
- skills: object with categories as keys and arrays as values
- education: array of education entries
- full_text: the complete resume as formatted text"""

    try:
        result = await gemini.generate_json(prompt)
        increment_usage(ip)
        return JSONResponse(content={
            "success": True,
            "data": result,
            "remaining_uses": remaining - 1,
        })
    except Exception as e:
        logger.error(f"Resume generation failed: {e}")
        raise HTTPException(status_code=500, detail="Generation failed, please try again")


@app.post("/api/captions")
async def generate_captions(request: Request, data: CaptionRequest):
    ip = request.client.host
    allowed, remaining = check_rate_limit(ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Daily free limit reached. Upgrade to Pro for unlimited access!"
        )

    lang = "Indonesian" if data.language == "id" else "English"
    count = min(data.count, 30)  # Max 30 captions

    prompt = f"""Generate {count} unique social media captions about: "{data.topic}"

Platform: {data.platform}
Tone: {data.tone}
Language: {lang}

Requirements:
- Each caption should be unique and engaging
- Include relevant emojis
- Include 3-5 relevant hashtags per caption
- For Twitter: max 280 characters per caption
- For Instagram: longer captions OK, use line breaks
- For LinkedIn: professional tone, can be longer
- For TikTok: short, trendy, with viral hashtags

Return as JSON array of objects:
[{{"caption": "...", "hashtags": ["..."], "platform": "{data.platform}"}}]"""

    try:
        result = await gemini.generate_json(prompt)
        increment_usage(ip)

        # Ensure it's a list
        if isinstance(result, dict) and "captions" in result:
            result = result["captions"]

        return JSONResponse(content={
            "success": True,
            "data": result if isinstance(result, list) else [result],
            "remaining_uses": remaining - 1,
        })
    except Exception as e:
        logger.error(f"Caption generation failed: {e}")
        raise HTTPException(status_code=500, detail="Generation failed, please try again")


@app.post("/api/email")
async def generate_email(request: Request, data: EmailRequest):
    ip = request.client.host
    allowed, remaining = check_rate_limit(ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Daily free limit reached. Upgrade to Pro for unlimited access!"
        )

    lang = "Indonesian" if data.language == "id" else "English"

    prompt = f"""Write a professional email for the following purpose:

Purpose: {data.purpose}
Context/Details: {data.context}
Tone: {data.tone}
Language: {lang}

Generate 3 versions of the email (short, medium, detailed).

Return as JSON with fields:
- subject: email subject line
- versions: array of 3 objects, each with:
  - length: "short", "medium", or "detailed"
  - body: the email body text
  - word_count: approximate word count
- tips: array of 2-3 tips for this type of email"""

    try:
        result = await gemini.generate_json(prompt)
        increment_usage(ip)
        return JSONResponse(content={
            "success": True,
            "data": result,
            "remaining_uses": remaining - 1,
        })
    except Exception as e:
        logger.error(f"Email generation failed: {e}")
        raise HTTPException(status_code=500, detail="Generation failed, please try again")


# ---------------------
# Payment Webhook (LemonSqueezy)
# ---------------------

@app.post("/webhook/payment")
async def payment_webhook(request: Request):
    """Handle LemonSqueezy payment webhooks."""
    import hashlib
    import hmac

    body = await request.body()
    signature = request.headers.get("X-Signature", "")

    secret = settings.saas.lemonsqueezy_webhook_secret
    if secret:
        expected = hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="Invalid signature")

    data = json.loads(body)
    event = data.get("meta", {}).get("event_name", "")

    if event == "order_created":
        email = data.get("data", {}).get("attributes", {}).get("user_email", "")
        logger.info(f"New payment from: {email}")
        # TODO: Add premium user to database

    return {"status": "ok"}


# ---------------------
# Health Check
# ---------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "tools": ["resume", "captions", "email"],
    }
