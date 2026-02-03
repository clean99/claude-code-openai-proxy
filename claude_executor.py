import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

from config import config
from models import ChatMessage
from tool_handler import build_tool_prompt, format_tool_results, get_schema_json

logger = logging.getLogger(__name__)


def merge_messages_to_prompt(messages: list[ChatMessage], include_tool_results: bool = False) -> tuple[str, str]:
    """
    Merge chat messages into a single prompt string.
    Returns (system_prompt, user_prompt)
    """
    system_parts = []
    conversation_parts = []

    for msg in messages:
        if msg.role == "system":
            system_parts.append(msg.content or "")
        elif msg.role == "user":
            content = msg.content or ""
            conversation_parts.append(f"User: {content}")
        elif msg.role == "assistant":
            content = msg.content or ""
            # Include tool_calls info if present
            if msg.tool_calls and include_tool_results:
                tool_calls_text = []
                for tc in msg.tool_calls:
                    tc_dict = tc.model_dump() if hasattr(tc, 'model_dump') else tc
                    func = tc_dict.get("function", {})
                    tool_calls_text.append(f"Called tool: {func.get('name')} with args: {func.get('arguments')}")
                if tool_calls_text:
                    content = content + "\n" + "\n".join(tool_calls_text) if content else "\n".join(tool_calls_text)
            if content:
                conversation_parts.append(f"Assistant: {content}")
        elif msg.role == "tool" and include_tool_results:
            # Tool result message - will be handled by format_tool_results
            pass

    system_prompt = "\n".join(system_parts) if system_parts else ""
    user_prompt = "\n\n".join(conversation_parts)

    # If only user messages without role prefix for single message
    if len(messages) == 1 and messages[0].role == "user":
        user_prompt = messages[0].content or ""
    elif len([m for m in messages if m.role not in ("system", "tool")]) == 1:
        # Single non-system, non-tool message, use content directly
        for msg in messages:
            if msg.role == "user":
                user_prompt = msg.content or ""
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


async def execute_claude_code_with_tools(
    messages: list[ChatMessage],
    tools: list[dict]
) -> dict:
    """
    Execute Claude Code CLI with tool calling support.
    Uses --json-schema for structured output.

    Returns:
        Raw JSON response from Claude Code CLI
    """
    # Build prompts
    system_prompt, user_prompt = merge_messages_to_prompt(messages, include_tool_results=True)

    # Add tool prompt to system
    tool_prompt = build_tool_prompt(tools)
    system_prompt = (system_prompt + "\n\n" + tool_prompt).strip() if system_prompt else tool_prompt

    # Add tool results if any
    tool_results_text = format_tool_results([m.model_dump() for m in messages])
    if tool_results_text:
        user_prompt = user_prompt + "\n\n" + tool_results_text

    # Build command - use JSON schema for structured output
    cmd = [
        config.claude_bin,
        "-p",
        "--dangerously-skip-permissions",
        "--output-format", "json",
        "--tools", "",  # Disable built-in tools
        "--json-schema", get_schema_json(),
        "--max-turns", "3",  # Need at least 2 turns for Claude Code internal processing
    ]

    # Add system prompt
    if system_prompt:
        cmd.extend(["--append-system-prompt", system_prompt])

    # Add user prompt
    cmd.append(user_prompt)

    logger.info(f"Executing Claude Code (tool mode): {' '.join(cmd[:8])}... [prompt truncated]")

    # Execute
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
        logger.error(f"Claude Code (tool mode) returned non-zero: {error_msg}")
        if not stdout:
            raise RuntimeError(f"Claude Code error: {error_msg}")

    output = stdout.decode()
    logger.debug(f"Claude Code (tool mode) raw output: {output[:500]}...")

    # Parse JSON output
    try:
        data = json.loads(output)
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude Code JSON output: {e}")
        # Return a fallback response
        return {
            "result": output,
            "structured_output": {
                "response_type": "text",
                "content": output
            }
        }


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
