"""
Tool calling handler for OpenAI-compatible tool calls.
Uses Claude Code CLI's --json-schema for structured output.
"""

import json
import uuid
from typing import Optional, Any

# JSON Schema for structured tool calling response
TOOL_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "response_type": {
            "type": "string",
            "enum": ["text", "tool_calls"]
        },
        "content": {
            "type": "string"
        },
        "tool_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "arguments": {"type": "object"}
                },
                "required": ["name", "arguments"]
            }
        }
    },
    "required": ["response_type"]
}


def get_schema_json() -> str:
    """Return JSON Schema string for --json-schema parameter."""
    return json.dumps(TOOL_RESPONSE_SCHEMA, separators=(',', ':'))


def build_tool_prompt(tools: list[dict]) -> str:
    """
    Convert OpenAI format tools to a prompt for Claude.

    Args:
        tools: List of OpenAI format tool definitions

    Returns:
        Prompt string describing available tools
    """
    if not tools:
        return ""

    tool_descriptions = []
    for tool in tools:
        if tool.get("type") == "function":
            func = tool["function"]
            name = func["name"]
            desc = func.get("description", "No description")
            params = func.get("parameters", {})

            # Format parameters
            param_lines = []
            if params.get("properties"):
                required_params = params.get("required", [])
                for pname, pinfo in params["properties"].items():
                    ptype = pinfo.get("type", "any")
                    pdesc = pinfo.get("description", "")
                    req_mark = "*" if pname in required_params else ""
                    param_lines.append(f"    - {pname}{req_mark} ({ptype}): {pdesc}")

            param_desc = "\n" + "\n".join(param_lines) if param_lines else ""
            tool_descriptions.append(f"- **{name}**: {desc}{param_desc}")

    return f"""## Available External Tools

The client application provides these tools for you to use. When you request a tool call, the CLIENT will execute it and return the results. Parameters marked with * are required.

{chr(10).join(tool_descriptions)}

## Response Instructions

Analyze the user's request and respond:

1. If the request requires external data or actions (weather, search, file operations, API calls, etc.):
   - Set "response_type" to "tool_calls"
   - List the tools in "tool_calls" array with "name" and "arguments"
   - The client will execute these tools and send you the results

2. ONLY if you can fully answer from your own knowledge (no external data needed):
   - Set "response_type" to "text"
   - Put your answer in "content"

CRITICAL: These tools are REAL and WORKING. The client will execute them. If the user needs external data, you MUST use the appropriate tool - do NOT say the tool is unavailable.
"""


def format_tool_results(messages: list[dict]) -> str:
    """
    Format tool result messages into text for Claude.

    Args:
        messages: List of message dicts, may include tool results

    Returns:
        Formatted string with tool results
    """
    results = []

    # Find the last assistant message with tool_calls to get tool names
    tool_names = {}
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                if isinstance(tc, dict):
                    tc_id = tc.get("id", "")
                    func = tc.get("function", {})
                    tool_names[tc_id] = func.get("name", "unknown")

    # Format tool results
    for msg in messages:
        if msg.get("role") == "tool":
            tool_call_id = msg.get("tool_call_id", "unknown")
            name = tool_names.get(tool_call_id, msg.get("name", "unknown_tool"))
            content = msg.get("content", "")
            results.append(f"### Tool Result: {name}\n```\n{content}\n```")

    if results:
        return "\n\n## Tool Execution Results\n\nThe following tools were executed and returned these results:\n\n" + "\n\n".join(results) + "\n\nNow provide your response based on these results."
    return ""


def parse_structured_output(response: dict) -> tuple[Optional[str], list[dict]]:
    """
    Parse Claude Code's structured_output and convert to OpenAI format.

    Args:
        response: Claude Code JSON response

    Returns:
        Tuple of (content, tool_calls)
    """
    structured = response.get("structured_output", {})

    if not structured:
        # Fallback: try to get from result field
        result = response.get("result", "")
        if result:
            return result, []
        return None, []

    response_type = structured.get("response_type", "text")

    if response_type == "text":
        content = structured.get("content", "")
        return content, []

    elif response_type == "tool_calls":
        tool_calls = []
        for call in structured.get("tool_calls", []):
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call.get("arguments", {}), ensure_ascii=False)
                }
            })
        content = structured.get("content")  # May be None
        return content, tool_calls

    # Unknown response_type, return as text
    return structured.get("content", ""), []


def should_use_tool_mode(request_tools: Optional[list], messages: list) -> bool:
    """
    Determine if we should use tool calling mode.

    Args:
        request_tools: Tools from the request
        messages: Messages from the request

    Returns:
        True if tool mode should be used
    """
    if not request_tools:
        return False

    # Check if there are any tool result messages (continuation of tool calling)
    for msg in messages:
        if msg.get("role") == "tool":
            return True
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            return True

    # Has tools defined, use tool mode
    return True
