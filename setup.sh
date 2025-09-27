#!/bin/bash

# WHOOP OAuth Server Setup Script
echo "🚀 Setting up WHOOP OAuth Server with virtual environment..."

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📚 Installing dependencies..."
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env file from template..."
    cp config.env.example .env
    echo "📝 Please edit .env file with your WHOOP credentials:"
    echo "   - WHOOP_CLIENT_ID=your_client_id_here"
    echo "   - WHOOP_CLIENT_SECRET=your_client_secret_here"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your WHOOP credentials"
echo "2. Run: source venv/bin/activate"
echo "3. Run: python whoop_oauth_server.py"
echo ""
echo "The server will be available at: http://localhost:5000"
