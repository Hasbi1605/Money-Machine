#!/bin/bash
# ============================================
# AI Money Machine - Quick Setup Script
# ============================================

set -e

echo "🤖 AI Money Machine - Setup"
echo "================================"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required. Install it first."
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✅ Python $PYTHON_VERSION detected"

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Create .env from example
if [ ! -f .env ]; then
    cp .env.example .env
    echo "📝 Created .env file - EDIT THIS with your API keys!"
else
    echo "✅ .env already exists"
fi

# Create required directories
mkdir -p output/articles output/videos output/thumbnails
mkdir -p logs data data/credentials

# Initialize database
echo "🗄️ Initializing database..."
python3 -c "
import asyncio
from shared.database import init_db
asyncio.run(init_db())
print('✅ Database initialized')
"

echo ""
echo "================================"
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your API keys (at minimum: GEMINI_API_KEY)"
echo "2. Get your Gemini API key from: https://aistudio.google.com/apikey"
echo "3. Run: python main.py --blog  (test blog pipeline)"
echo "4. Run: python main.py         (start full automation)"
echo ""
echo "Optional setup:"
echo "  - WordPress, Medium, or Blogger credentials for auto-publishing"
echo "  - Pexels API key for stock footage (free: https://www.pexels.com/api/)"
echo "  - YouTube API credentials for auto-upload"
echo "  - Telegram bot for notifications"
echo "================================"
