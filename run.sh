#!/bin/bash

# WHOOP OAuth Server Run Script
echo "🚀 Starting WHOOP OAuth Server..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Please run ./setup.sh first."
    exit 1
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Please run ./setup.sh first."
    exit 1
fi

# Start the server
echo "🌐 Starting server at http://localhost:8080"
echo "Press Ctrl+C to stop the server"
echo ""
python whoop_oauth_server.py
