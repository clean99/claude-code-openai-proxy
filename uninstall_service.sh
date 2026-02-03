#!/bin/bash
# Uninstall Claude Code OpenAI Proxy launchd service

PLIST_NAME="com.claude-code.openai-proxy.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "Uninstalling Claude Code OpenAI Proxy service..."

# Unload the service
if launchctl list | grep -q "com.claude-code.openai-proxy"; then
    echo "Stopping service..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

# Remove plist
if [ -f "$PLIST_DST" ]; then
    echo "Removing launch agent..."
    rm "$PLIST_DST"
fi

echo "Service uninstalled successfully!"
