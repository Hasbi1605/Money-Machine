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
from shared.database import init_db, add_premium_user, is_premium_user, log_revenue

# ---------------------
# App Setup
# ---------------------

app = FastAPI(
    title="AI Writing Tools",
    description="Free AI-powered writing tools",
    version="1.0.0",
)


@app.on_event("startup")
async def startup():
    await init_db()

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
PREMIUM_USES_PER_DAY = 100
usage_tracker: dict = {}  # IP -> {"date": date, "count": int}
premium_cache: dict = {}  # email -> is_premium (cached for the session)


def check_rate_limit(ip: str) -> tuple[bool, int]:
    """Check if an IP has remaining free uses. Returns (allowed, remaining)."""
    today = date.today().isoformat()

    if ip not in usage_tracker or usage_tracker[ip]["date"] != today:
        usage_tracker[ip] = {"date": today, "count": 0}

    count = usage_tracker[ip]["count"]
    limit = usage_tracker[ip].get("limit", FREE_USES_PER_DAY)
    remaining = limit - count

    if remaining <= 0:
        return False, 0

    return True, remaining


async def check_premium_rate_limit(ip: str, email: str = "") -> tuple[bool, int]:
    """Check rate limit with premium support."""
    today = date.today().isoformat()

    if ip not in usage_tracker or usage_tracker[ip]["date"] != today:
        usage_tracker[ip] = {"date": today, "count": 0, "limit": FREE_USES_PER_DAY}

    # Check premium status
    if email and email not in premium_cache:
        try:
            premium_cache[email] = await is_premium_user(email)
        except Exception:
            premium_cache[email] = False

    if email and premium_cache.get(email):
        usage_tracker[ip]["limit"] = PREMIUM_USES_PER_DAY

    count = usage_tracker[ip]["count"]
    limit = usage_tracker[ip].get("limit", FREE_USES_PER_DAY)
    remaining = limit - count

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
# Payment - Midtrans (QRIS, GoPay, ShopeePay, Dana, OVO)
# ---------------------

def get_snap_client():
    """Create Midtrans Snap client."""
    import midtransclient
    return midtransclient.Snap(
        is_production=settings.saas.midtrans_is_production,
        server_key=settings.saas.midtrans_server_key,
        client_key=settings.saas.midtrans_client_key,
    )


@app.post("/api/create-payment")
async def create_payment(request: Request):
    """Create Midtrans Snap payment token for Pro upgrade."""
    body = await request.json()
    email = body.get("email", "").strip()
    
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email tidak valid")
    
    if not settings.saas.midtrans_server_key:
        raise HTTPException(status_code=503, detail="Payment belum dikonfigurasi")
    
    # Check if already premium
    if await is_premium_user(email):
        return JSONResponse(content={"success": False, "message": "Kamu sudah Pro!"})
    
    import uuid
    order_id = f"PRO-{uuid.uuid4().hex[:8].upper()}-{int(datetime.utcnow().timestamp())}"
    
    snap = get_snap_client()
    
    param = {
        "transaction_details": {
            "order_id": order_id,
            "gross_amount": settings.saas.pro_price,
        },
        "item_details": [{
            "id": "ai-writing-pro",
            "price": settings.saas.pro_price,
            "quantity": 1,
            "name": "AI Writing Tools Pro (1 Bulan)",
        }],
        "customer_details": {
            "email": email,
        },
        "enabled_payments": [
            "gopay", "shopeepay", "dana", "ovo", "qris",
            "bca_va", "bni_va", "bri_va", "permata_va", "other_va",
        ],
    }
    
    try:
        snap_response = snap.create_transaction(param)
        logger.info(f"Payment created: {order_id} for {email}")
        return JSONResponse(content={
            "success": True,
            "snap_token": snap_response["token"],
            "redirect_url": snap_response["redirect_url"],
            "order_id": order_id,
        })
    except Exception as e:
        logger.error(f"Midtrans error: {e}")
        raise HTTPException(status_code=500, detail="Gagal membuat pembayaran")


@app.post("/webhook/midtrans")
async def midtrans_webhook(request: Request):
    """Handle Midtrans payment notification webhook."""
    import hashlib
    
    body = await request.json()
    
    order_id = body.get("order_id", "")
    status_code = body.get("status_code", "")
    gross_amount = body.get("gross_amount", "")
    signature_key = body.get("signature_key", "")
    transaction_status = body.get("transaction_status", "")
    fraud_status = body.get("fraud_status", "accept")
    
    # Verify signature
    server_key = settings.saas.midtrans_server_key
    if server_key:
        raw = f"{order_id}{status_code}{gross_amount}{server_key}"
        expected_signature = hashlib.sha512(raw.encode()).hexdigest()
        if signature_key != expected_signature:
            logger.warning(f"Invalid Midtrans signature for {order_id}")
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    logger.info(f"Midtrans webhook: {order_id} status={transaction_status}")
    
    # Payment successful
    if transaction_status in ("capture", "settlement"):
        if fraud_status == "accept":
            # Extract email from Midtrans notification
            # We need to verify the transaction to get customer details
            try:
                snap = get_snap_client()
                import midtransclient
                core = midtransclient.CoreApi(
                    is_production=settings.saas.midtrans_is_production,
                    server_key=settings.saas.midtrans_server_key,
                    client_key=settings.saas.midtrans_client_key,
                )
                tx_detail = core.transactions.status(order_id)
                
                # Try multiple fields for email
                email = ""
                if "customer_details" in tx_detail:
                    email = tx_detail["customer_details"].get("email", "")
                if not email:
                    # Fallback: try notification body
                    email = body.get("email", "")
                
                if email:
                    await add_premium_user(email, "pro")
                    amount = float(gross_amount) if gross_amount else 0
                    await log_revenue(
                        source="midtrans",
                        amount=amount,
                        currency="IDR",
                        description=f"Pro upgrade: {email} (order: {order_id})"
                    )
                    premium_cache[email] = True
                    logger.info(f"New premium user: {email}, Rp {gross_amount}")
                else:
                    logger.warning(f"Payment {order_id} success but no email found")
                    
            except Exception as e:
                logger.error(f"Error processing payment {order_id}: {e}")
    
    elif transaction_status in ("deny", "cancel", "expire"):
        logger.info(f"Payment {order_id} failed/expired: {transaction_status}")
    
    elif transaction_status == "pending":
        logger.info(f"Payment {order_id} pending")
    
    return {"status": "ok"}


# ---------------------
# Pricing Page
# ---------------------

@app.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request):
    client_key = settings.saas.midtrans_client_key
    is_production = settings.saas.midtrans_is_production
    return templates.TemplateResponse("pricing.html", {
        "request": request,
        "client_key": client_key,
        "is_production": is_production,
        "pro_price": settings.saas.pro_price,
    })


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
