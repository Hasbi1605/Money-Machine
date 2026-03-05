#!/bin/bash
# ============================================
# AI Money Machine - VPS Deployment Script
# For DigitalOcean, Hetzner, or any Ubuntu VPS
# ============================================

set -e

echo "🚀 AI Money Machine - VPS Deployment"
echo "======================================"

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11+, pip, venv
sudo apt install -y python3 python3-pip python3-venv

# Install ffmpeg (required for moviepy/video processing)
sudo apt install -y ffmpeg

# Install ImageMagick (for text overlays in videos)
sudo apt install -y imagemagick

# Fix ImageMagick policy for MoviePy
sudo sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@*"/' /etc/ImageMagick-6/policy.xml 2>/dev/null || true

# Clone or copy your project
# git clone YOUR_REPO_URL ai-money-machine
cd /root/ai-money-machine  # Adjust path as needed

# Run setup
bash setup.sh

echo ""
echo "🔧 Setting up systemd services..."

# Create systemd service for the scheduler
sudo tee /etc/systemd/system/ai-money-machine.service > /dev/null <<EOF
[Unit]
Description=AI Money Machine Scheduler
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/ai-money-machine
ExecStart=/root/ai-money-machine/.venv/bin/python main.py
Restart=always
RestartSec=30
Environment=PATH=/root/ai-money-machine/.venv/bin:/usr/local/bin:/usr/bin

[Install]
WantedBy=multi-user.target
EOF

# Create systemd service for the SaaS app
sudo tee /etc/systemd/system/ai-saas.service > /dev/null <<EOF
[Unit]
Description=AI Writing Tools SaaS
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/ai-money-machine
ExecStart=/root/ai-money-machine/.venv/bin/python main.py --saas
Restart=always
RestartSec=10
Environment=PATH=/root/ai-money-machine/.venv/bin:/usr/local/bin:/usr/bin

[Install]
WantedBy=multi-user.target
EOF

# Create systemd service for dashboard
sudo tee /etc/systemd/system/ai-dashboard.service > /dev/null <<EOF
[Unit]
Description=AI Money Machine Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/ai-money-machine
ExecStart=/root/ai-money-machine/.venv/bin/python main.py --dashboard
Restart=always
RestartSec=10
Environment=PATH=/root/ai-money-machine/.venv/bin:/usr/local/bin:/usr/bin

[Install]
WantedBy=multi-user.target
EOF

# Enable and start services
sudo systemctl daemon-reload
sudo systemctl enable ai-money-machine ai-saas ai-dashboard
sudo systemctl start ai-money-machine ai-saas ai-dashboard

echo ""
echo "======================================"
echo "✅ Deployment complete!"
echo ""
echo "Services running:"
echo "  📅 Scheduler: systemctl status ai-money-machine"
echo "  🌐 SaaS App:  http://YOUR_IP:8000"
echo "  📊 Dashboard:  http://YOUR_IP:8001"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status ai-money-machine  # Check scheduler"
echo "  sudo journalctl -u ai-money-machine -f   # View live logs"
echo "  sudo systemctl restart ai-money-machine   # Restart scheduler"
echo "======================================"
