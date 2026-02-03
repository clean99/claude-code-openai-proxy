import os
import shutil
from dataclasses import dataclass


@dataclass
class Config:
    """Configuration for Claude OpenAI Proxy"""

    # Server settings
    host: str = "0.0.0.0"
    port: int = 18880

    # Claude Code CLI path
    claude_bin: str = ""

    # Optional auth token (empty = no auth)
    proxy_token: str = ""

    # Model name exposed to clients
    model_name: str = "claude-code"
    model_display_name: str = "Claude Code Proxy (local)"

    # Claude Code CLI options
    max_turns: int = 10
    timeout: int = 300  # seconds

    def __post_init__(self):
        # Try to find claude binary
        self.claude_bin = os.environ.get("CLAUDE_BIN", "")
        if not self.claude_bin:
            # Try to find in PATH
            claude_path = shutil.which("claude")
            if claude_path:
                self.claude_bin = claude_path
            else:
                self.claude_bin = "claude"  # Assume it's in PATH

        self.proxy_token = os.environ.get("CLAUDE_PROXY_TOKEN", "")
        self.host = os.environ.get("PROXY_HOST", self.host)
        self.port = int(os.environ.get("PROXY_PORT", self.port))
        self.max_turns = int(os.environ.get("CLAUDE_MAX_TURNS", self.max_turns))
        self.timeout = int(os.environ.get("CLAUDE_TIMEOUT", self.timeout))


config = Config()
