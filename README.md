# 🤖 AI Money Machine

**Sistem otomasi penghasil uang menggunakan AI, berjalan 24/7 dengan minimal campur tangan.**

## Arsitektur

```
ai-money-machine/
├── main.py                    # Main runner & scheduler
├── setup.sh                   # Quick setup script
├── deploy_vps.sh              # VPS deployment script
├── requirements.txt
├── .env.example               # Template konfigurasi
│
├── shared/                    # Shared modules
│   ├── config.py              # Central configuration
│   ├── gemini_client.py       # Gemini API wrapper (rate limited)
│   ├── database.py            # SQLite database for tracking
│   ├── notifier.py            # Telegram notifications
│   └── logger.py              # Logging setup
│
├── blog_engine/               # Pipeline 1: Auto-Blog SEO
│   ├── keyword_researcher.py  # Google Suggest + Gemini analysis
│   ├── article_generator.py   # SEO article generation + affiliates
│   ├── publisher.py           # WordPress, Medium, Blogger auto-publish
│   ├── affiliate_config.json  # Affiliate program settings
│   └── orchestrator.py        # Full blog pipeline
│
├── video_engine/              # Pipeline 2: Faceless YouTube
│   ├── script_writer.py       # Video script generation
│   ├── tts_engine.py          # Edge-TTS (free text-to-speech)
│   ├── video_assembler.py     # MoviePy + Pexels stock footage
│   ├── uploader.py            # YouTube auto-upload
│   └── orchestrator.py        # Full video pipeline
│
├── saas_app/                  # Pipeline 3: Micro-SaaS
│   ├── app.py                 # FastAPI backend (3 AI tools)
│   ├── templates/             # Frontend HTML templates
│   │   ├── index.html         # Landing page
│   │   ├── resume.html        # AI Resume Builder
│   │   ├── captions.html      # AI Caption Generator
│   │   └── email.html         # AI Email Writer
│   └── static/
│
├── dashboard/                 # Monitoring
│   └── app.py                 # Stats dashboard
│
├── output/                    # Generated content
│   ├── articles/
│   └── videos/
├── data/                      # Database & credentials
└── logs/                      # Application logs
```

## Quick Start

### 1. Setup (Lokal)

```bash
# Clone dan setup
cd ai-money-machine
chmod +x setup.sh
bash setup.sh
```

### 2. Konfigurasi API Keys

Edit `.env` file — **minimum yang diperlukan**:

```env
# WAJIB - ambil dari https://aistudio.google.com/apikey
GEMINI_API_KEY=your_gemini_api_key_here
```

**Opsional (tambahkan sesuai kebutuhan):**

| Key                        | Untuk Apa                  | Cara Dapatkan                                                         |
| -------------------------- | -------------------------- | --------------------------------------------------------------------- |
| `GEMINI_API_KEY`           | **Otak AI** (wajib)        | [Google AI Studio](https://aistudio.google.com/apikey) — GRATIS       |
| `PEXELS_API_KEY`           | Stock footage video        | [Pexels API](https://www.pexels.com/api/) — GRATIS                    |
| `WP_URL` + credentials     | Auto-publish ke WordPress  | WordPress > Settings > App Password                                   |
| `MEDIUM_TOKEN`             | Auto-publish ke Medium     | [Medium Settings](https://medium.com/me/settings) > Integration Token |
| `YOUTUBE_CLIENT_ID/SECRET` | Upload video ke YouTube    | [Google Cloud Console](https://console.cloud.google.com)              |
| `TELEGRAM_BOT_TOKEN`       | Notifikasi monitoring      | [@BotFather](https://t.me/botfather) di Telegram                      |
| `AMAZON_AFFILIATE_TAG`     | Affiliate links di artikel | [Amazon Associates](https://affiliate-program.amazon.com/)            |

### 3. Test Pipeline

```bash
# Aktifkan virtual environment
source .venv/bin/activate

# Test blog pipeline (generate 1 article per language)
python main.py --blog

# Test video pipeline (generate 1 video)
python main.py --video

# Start SaaS web app (http://localhost:8000)
python main.py --saas

# Start monitoring dashboard (http://localhost:8001)
python main.py --dashboard
```

### 4. Jalankan Full Automation

```bash
# Start scheduler (blog setiap 12 jam, video setiap 24 jam)
python main.py
```

## Deploy ke VPS

```bash
# Di VPS (Ubuntu), upload project lalu:
chmod +x deploy_vps.sh
bash deploy_vps.sh
```

Ini akan:

- Install dependencies (Python, ffmpeg, ImageMagick)
- Setup systemd services (auto-start on boot)
- Jalankan 3 services: Scheduler, SaaS App (port 8000), Dashboard (port 8001)

## Revenue Streams

| Pipeline             | Sumber Revenue                                       | Timeline  |
| -------------------- | ---------------------------------------------------- | --------- |
| **Auto-Blog**        | Affiliate links (Amazon, Tokopedia, Shopee), AdSense | 1-3 bulan |
| **Faceless YouTube** | YouTube AdSense, affiliate di deskripsi              | 3-6 bulan |
| **Micro-SaaS**       | Freemium subscription ($5/bulan per user)            | 1-2 bulan |

## Jadwal Otomatis

| Pipeline     | Frekuensi         | Output per Bulan |
| ------------ | ----------------- | ---------------- |
| Blog (EN)    | Setiap 12 jam     | ~60 artikel      |
| Blog (ID)    | Setiap 12 jam     | ~60 artikel      |
| Video (EN)   | Setiap 24 jam     | ~30 video        |
| Video (ID)   | Setiap 24 jam     | ~30 video        |
| SaaS         | 24/7 online       | N/A              |
| Daily Report | Setiap hari 23:59 | Telegram notif   |

## Biaya Operasional

| Item              | Biaya/Bulan                        |
| ----------------- | ---------------------------------- |
| Gemini API        | **$0** (free tier: 1M tokens/hari) |
| Edge-TTS          | **$0** (unlimited)                 |
| Pexels API        | **$0** (200 requests/jam)          |
| VPS Hosting       | **$5-10** (DigitalOcean/Hetzner)   |
| Domain (optional) | **$1/bulan**                       |
| **TOTAL**         | **~$5-10/bulan**                   |

## Monitoring

- **Dashboard**: `http://YOUR_IP:8001` — stats, recent runs, errors
- **Telegram Bot**: Notifikasi real-time setiap pipeline selesai/error
- **Logs**: `logs/` folder — daily log files + error log terpisah
- **Database**: `data/money_machine.db` — SQLite tracking semua konten

## Troubleshooting

```bash
# Cek status services (VPS)
sudo systemctl status ai-money-machine
sudo systemctl status ai-saas

# Lihat logs real-time
sudo journalctl -u ai-money-machine -f

# Restart jika error
sudo systemctl restart ai-money-machine

# Test Gemini API
python3 -c "
from shared.gemini_client import gemini
import asyncio
result = asyncio.run(gemini.generate('Say hello'))
print(result)
"
```

## Catatan Penting

1. **Kualitas Konten**: Review manual 1-2x/minggu untuk memastikan kualitas tetap baik
2. **Platform Policy**: Jangan spam — 2 artikel/hari dan 1 video/hari adalah aman
3. **Diversifikasi**: Gunakan beberapa blog/channel untuk mengurangi risiko
4. **SEO**: Hasil SEO butuh 1-3 bulan untuk terlihat, bersabarlah
5. **Affiliate**: Daftar ke affiliate program SEBELUM mulai — perlu approval
