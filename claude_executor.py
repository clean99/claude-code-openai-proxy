import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

from config import config
from models import ChatMessage

logger = logging.getLogger(__name__)


def merge_messages_to_prompt(messages: list[ChatMessage]) -> tuple[str, str]:
    """
    Merge chat messages into a single prompt string.
    Returns (system_prompt, user_prompt)
    """
    system_parts = []
    conversation_parts = []

    for msg in messages:
        if msg.role == "system":
            system_parts.append(msg.content)
        elif msg.role == "user":
            conversation_parts.append(f"User: {msg.content}")
        elif msg.role == "assistant":
            conversation_parts.append(f"Assistant: {msg.content}")

    system_prompt = "\n".join(system_parts) if system_parts else ""
    user_prompt = "\n\n".join(conversation_parts)

    # If only user messages without role prefix for single message
    if len(messages) == 1 and messages[0].role == "user":
        user_prompt = messages[0].content
    elif len([m for m in messages if m.role != "system"]) == 1:
        # Single non-system message, use content directly
        for msg in messages:
            if msg.role == "user":
                user_prompt = msg.content
                break

    return system_prompt, user_prompt


async def execute_claude_code(
    messages: list[ChatMessage],
    stream: bool = False
) -> AsyncGenerator[str, None]:
    """
    Execute Claude Code CLI and yield response content.
    Uses --dangerously-skip-permissions for full automation.
    """
    system_prompt, user_prompt = merge_messages_to_prompt(messages)

    # Build command
    cmd = [
        config.claude_bin,
        "-p",  # Print mode (non-interactive)
        "--dangerously-skip-permissions",  # Full permissions, no user interaction
        "--output-format", "stream-json" if stream else "json",
        "--max-turns", str(config.max_turns),
    ]

    # stream-json requires --verbose flag
    if stream:
        cmd.append("--verbose")

    # Add system prompt if present
    if system_prompt:
        cmd.extend(["--append-system-prompt", system_prompt])

    # Add the user prompt
    cmd.append(user_prompt)

    logger.info(f"Executing Claude Code: {' '.join(cmd[:6])}... [prompt truncated]")

    try:
        if stream:
            async for chunk in _execute_streaming(cmd):
                yield chunk
        else:
            result = await _execute_blocking(cmd)
            yield result
    except Exception as e:
        logger.error(f"Claude Code execution error: {e}")
        yield f"Error executing Claude Code: {str(e)}"


async def _execute_blocking(cmd: list[str]) -> str:
    """Execute command and return full response."""
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=config.timeout
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise TimeoutError(f"Claude Code execution timed out after {config.timeout}s")

    if process.returncode != 0:
        error_msg = stderr.decode() if stderr else "Unknown error"
        logger.error(f"Claude Code returned non-zero: {error_msg}")
        # Still try to parse stdout if available
        if not stdout:
            raise RuntimeError(f"Claude Code error: {error_msg}")

    output = stdout.decode()

    # Parse JSON output
    try:
        data = json.loads(output)
        # Extract result from Claude Code JSON response
        if isinstance(data, dict):
            if "result" in data:
                return data["result"]
            elif "content" in data:
                return data["content"]
            elif "message" in data:
                return data["message"]
        return output
    except json.JSONDecodeError:
        # Return raw output if not valid JSON
        return output


async def _execute_streaming(cmd: list[str]) -> AsyncGenerator[str, None]:
    """Execute command and stream response chunks."""
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    buffer = ""

    try:
        while True:
            chunk = await asyncio.wait_for(
                process.stdout.read(1024),
                timeout=config.timeout
            )

            if not chunk:
                break

            buffer += chunk.decode()

            # Process complete JSON lines (stream-json format is newline-delimited)
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()

                if not line:
                    continue

                try:
                    data = json.loads(line)
                    # Extract content from streaming event
                    content = _extract_streaming_content(data)
                    if content:
                        yield content
                except json.JSONDecodeError:
                    # Non-JSON line, yield as-is
                    if line:
                        yield line

        # Process remaining buffer
        if buffer.strip():
            try:
                data = json.loads(buffer.strip())
                content = _extract_streaming_content(data)
                if content:
                    yield content
            except json.JSONDecodeError:
                yield buffer.strip()

    except asyncio.TimeoutError:
        process.kill()
        raise TimeoutError(f"Claude Code streaming timed out after {config.timeout}s")
    finally:
        await process.wait()


def _extract_streaming_content(data: dict) -> Optional[str]:
    """Extract content from a streaming JSON event."""
    if not isinstance(data, dict):
        return None

    # Handle different event types from Claude Code stream-json
    event_type = data.get("type", "")

    if event_type == "assistant":
        # Assistant message event - extract text from content blocks
        message = data.get("message", {})
        if isinstance(message, dict):
            content = message.get("content", "")
            if isinstance(content, list):
                # Content blocks
                texts = [b.get("text", "") for b in content if b.get("type") == "text"]
                return "".join(texts)
            return content if content else None
    elif event_type == "content_block_delta":
        # Content delta event
        delta = data.get("delta", {})
        return delta.get("text", "")
    # Skip "result" event to avoid duplicating content already sent via "assistant"
    # The "result" event contains the same text as the "assistant" event

    return None
