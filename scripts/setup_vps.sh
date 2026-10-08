#!/bin/bash
# ASR Engine v3 — GCP Ubuntu VPS Setup Script
# Run this script on your Google Cloud e2-micro instance

echo "🚀 Starting ASR Engine v3 GCP Deployment..."

# 1. Update system and install dependencies
echo "📦 Installing system dependencies..."
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y python3-pip python3-venv git

# 2. Setup project directory and virtual environment
echo "🐍 Setting up Python environment..."
cd ~
if [ ! -d "ASR-Execution-Engine" ]; then
    echo "⚠️ Project directory not found! Please upload the files to ~/ASR-Execution-Engine"
    exit 1
fi

cd ASR-Execution-Engine
python3 -m venv venv
source venv/bin/activate
pip install wheel
pip install -e .

# 3. Create Systemd Service for 24/7 background execution
echo "⚙️ Creating systemd background service..."
SERVICE_FILE="/etc/systemd/system/asr-bot.service"

sudo bash -c "cat > $SERVICE_FILE" << EOF
[Unit]
Description=ASR Engine v3 Auto-Trader
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/$USER/ASR-Execution-Engine
ExecStart=/home/$USER/ASR-Execution-Engine/venv/bin/python -m live_trading.auto_trader
Restart=always
RestartSec=10
Environment="PYTHONIOENCODING=utf-8"

[Install]
WantedBy=multi-user.target
EOF

# 4. Enable and start the service
echo "🔥 Starting the bot..."
sudo systemctl daemon-reload
sudo systemctl enable asr-bot
sudo systemctl start asr-bot

echo ""
echo "=========================================================="
echo "✅ DEPLOYMENT COMPLETE!"
echo "The ASR bot is now running in the background 24/7."
echo ""
echo "To check the live logs, run:"
echo "  sudo journalctl -u asr-bot -f"
echo ""
echo "To stop the bot, run:"
echo "  sudo systemctl stop asr-bot"
echo "=========================================================="
