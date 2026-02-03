#!/bin/bash
# Claude Code OpenAI Proxy Startup Script

# Change to script directory
cd "$(dirname "$0")"

# Optional: Set environment variables
# export CLAUDE_BIN="/path/to/claude"
# export CLAUDE_PROXY_TOKEN="your-secret-token"
# export PROXY_PORT=18880
# export CLAUDE_MAX_TURNS=10
# export CLAUDE_TIMEOUT=300

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Check if claude is available
if ! command -v claude &> /dev/null; then
    echo "Warning: 'claude' command not found in PATH"
    echo "Please set CLAUDE_BIN environment variable to the path of claude binary"
fi

# Start the server
echo "Starting Claude Code OpenAI Proxy..."
python main.py
