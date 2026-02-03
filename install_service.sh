#!/bin/bash
# Install Claude Code OpenAI Proxy as a macOS launchd service

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.claude-code.openai-proxy.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

# Find claude binary
CLAUDE_BIN=$(which claude 2>/dev/null || echo "$HOME/.local/bin/claude")
if [ ! -x "$CLAUDE_BIN" ]; then
    echo "Error: Claude Code CLI not found. Please install it first."
    exit 1
fi

echo "Installing Claude Code OpenAI Proxy service..."
echo "  Project dir: $SCRIPT_DIR"
echo "  Claude bin:  $CLAUDE_BIN"

# Create logs directory
mkdir -p "$SCRIPT_DIR/logs"

# Ensure venv exists and dependencies installed
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/venv"
fi

echo "Installing dependencies..."
"$SCRIPT_DIR/venv/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"

# Create LaunchAgents directory if not exists
mkdir -p "$HOME/Library/LaunchAgents"

# Unload existing service if running
if launchctl list | grep -q "com.claude-code.openai-proxy"; then
    echo "Stopping existing service..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

# Generate plist file with correct paths
echo "Generating launch agent plist..."
cat > "$PLIST_DST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude-code.openai-proxy</string>

    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_DIR/venv/bin/python</string>
        <string>$SCRIPT_DIR/main.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin</string>
        <key>CLAUDE_BIN</key>
        <string>$CLAUDE_BIN</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/logs/stdout.log</string>

    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/logs/stderr.log</string>
</dict>
</plist>
EOF

# Load the service
echo "Starting service..."
launchctl load "$PLIST_DST"

echo ""
echo "Service installed successfully!"
echo ""
echo "Commands:"
echo "  Restart: launchctl kickstart -k gui/\$(id -u)/com.claude-code.openai-proxy"
echo "  Stop:    launchctl unload ~/Library/LaunchAgents/$PLIST_NAME"
echo "  Status:  launchctl list | grep claude-code"
echo "  Logs:    tail -f $SCRIPT_DIR/logs/stderr.log"
echo ""
echo "Service URL: http://127.0.0.1:18880"
