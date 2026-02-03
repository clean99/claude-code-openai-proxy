#!/usr/bin/env python3
"""
Claude Code OpenAI-Compatible Proxy Server

This server wraps Claude Code CLI as an OpenAI-compatible API endpoint.
It exposes /v1/chat/completions and /v1/models endpoints.

Supports:
- Basic chat completions
- Streaming responses
- Tool calling (function calling)

Usage:
    python main.py

Environment Variables:
    CLAUDE_BIN: Path to claude binary (default: auto-detect)
    CLAUDE_PROXY_TOKEN: Optional auth token (default: no auth)
    PROXY_HOST: Server host (default: 0.0.0.0)
    PROXY_PORT: Server port (default: 18880)
    CLAUDE_MAX_TURNS: Max agentic turns (default: 10)
    CLAUDE_TIMEOUT: Execution timeout in seconds (default: 300)
"""

import logging
import time
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from config import config
from models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
    ResponseMessage,
    ToolCall,
    FunctionCall,
    Usage,
    ModelInfo,
    ModelListResponse,
)
from claude_executor import execute_claude_code, execute_claude_code_with_tools
from tool_handler import parse_structured_output

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Claude Code OpenAI Proxy",
    description="OpenAI-compatible API proxy for Claude Code CLI with tool calling support",
    version="1.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation errors with request body for debugging."""
    body = await request.body()
    logger.error(f"Validation error for {request.url.path}")
    logger.error(f"Request body: {body.decode()[:2000]}")
    logger.error(f"Validation errors: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


def verify_token(authorization: Optional[str]) -> bool:
    """Verify the authorization token if configured."""
    if not config.proxy_token:
        return True  # No auth required

    if not authorization:
        return False

    # Support both "Bearer token" and raw token
    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]

    return token == config.proxy_token


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "claude-code-openai-proxy",
        "version": "1.1.0",
        "features": ["chat", "streaming", "tool_calling"],
    }


@app.get("/v1/models")
@app.get("/models")
async def list_models(authorization: Optional[str] = Header(None)):
    """List available models (OpenAI-compatible)."""
    if not verify_token(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")

    return ModelListResponse(
        data=[
            ModelInfo(
                id=config.model_name,
                created=int(time.time()),
                owned_by="claude-code-proxy",
            )
        ]
    )


@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Create chat completion (OpenAI-compatible).
    Supports tool calling when tools are provided.
    """
    if not verify_token(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")

    request_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    has_tools = request.tools and len(request.tools) > 0
    logger.info(f"Request {request_id}: model={request.model}, messages={len(request.messages)}, stream={request.stream}, tools={has_tools}")
    if has_tools:
        tool_names = [t.function.name for t in request.tools]
        logger.info(f"Request {request_id}: Tool names: {tool_names}")

    # Tool calling mode
    if has_tools:
        logger.info(f"Request {request_id}: Tool calling mode with {len(request.tools)} tools")
        return await _tool_calling_response(request_id, request)

    # Normal mode
    if request.stream:
        return EventSourceResponse(
            _stream_response(request_id, request),
            media_type="text/event-stream",
        )
    else:
        return await _blocking_response(request_id, request)


async def _tool_calling_response(request_id: str, request: ChatCompletionRequest) -> ChatCompletionResponse:
    """Generate a response with potential tool calls."""
    # Convert tools to dict format
    tools_dict = [t.model_dump() for t in request.tools]

    # Execute with tool support
    raw_response = await execute_claude_code_with_tools(request.messages, tools_dict)

    # Parse structured output
    content, tool_calls = parse_structured_output(raw_response)

    logger.info(f"Request {request_id}: Tool response - content={bool(content)}, tool_calls={len(tool_calls)}")
    if content and not tool_calls:
        logger.info(f"Request {request_id}: Text response: {content[:200]}...")

    # Build response
    if tool_calls:
        # Convert tool_calls to proper format
        formatted_tool_calls = [
            ToolCall(
                id=tc["id"],
                type=tc["type"],
                function=FunctionCall(
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"]
                )
            )
            for tc in tool_calls
        ]

        return ChatCompletionResponse(
            id=request_id,
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ResponseMessage(
                        role="assistant",
                        content=content,
                        tool_calls=formatted_tool_calls,
                    ),
                    finish_reason="tool_calls",
                )
            ],
            usage=_estimate_usage(request, content or ""),
        )
    else:
        return ChatCompletionResponse(
            id=request_id,
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ResponseMessage(
                        role="assistant",
                        content=content or "",
                    ),
                    finish_reason="stop",
                )
            ],
            usage=_estimate_usage(request, content or ""),
        )


async def _blocking_response(request_id: str, request: ChatCompletionRequest) -> ChatCompletionResponse:
    """Generate a blocking (non-streaming) response."""
    content_parts = []

    async for chunk in execute_claude_code(request.messages, stream=False):
        content_parts.append(chunk)

    full_content = "".join(content_parts)

    return ChatCompletionResponse(
        id=request_id,
        model=request.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ResponseMessage(
                    role="assistant",
                    content=full_content,
                ),
                finish_reason="stop",
            )
        ],
        usage=_estimate_usage(request, full_content),
    )


async def _stream_response(request_id: str, request: ChatCompletionRequest):
    """Generate a streaming SSE response."""
    # Send initial chunk with role
    initial_chunk = ChatCompletionChunk(
        id=request_id,
        model=request.model,
        choices=[
            ChatCompletionChunkChoice(
                index=0,
                delta=ChatCompletionChunkDelta(role="assistant"),
                finish_reason=None,
            )
        ],
    )
    yield {"data": initial_chunk.model_dump_json()}

    # Stream content chunks
    async for content in execute_claude_code(request.messages, stream=True):
        if content:
            chunk = ChatCompletionChunk(
                id=request_id,
                model=request.model,
                choices=[
                    ChatCompletionChunkChoice(
                        index=0,
                        delta=ChatCompletionChunkDelta(content=content),
                        finish_reason=None,
                    )
                ],
            )
            yield {"data": chunk.model_dump_json()}

    # Send final chunk with finish_reason
    final_chunk = ChatCompletionChunk(
        id=request_id,
        model=request.model,
        choices=[
            ChatCompletionChunkChoice(
                index=0,
                delta=ChatCompletionChunkDelta(),
                finish_reason="stop",
            )
        ],
    )
    yield {"data": final_chunk.model_dump_json()}
    yield {"data": "[DONE]"}


def _estimate_usage(request: ChatCompletionRequest, completion: str) -> Usage:
    """Estimate token usage (rough approximation)."""
    prompt_tokens = 0
    for m in request.messages:
        if m.content:
            prompt_tokens += len(str(m.content).split()) * 2

    completion_tokens = len(completion.split()) * 2

    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Claude Code OpenAI Proxy on {config.host}:{config.port}")
    logger.info(f"Claude binary: {config.claude_bin}")
    logger.info(f"Model name: {config.model_name}")
    logger.info(f"Auth required: {bool(config.proxy_token)}")
    logger.info("Features: chat, streaming, tool_calling")

    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="info",
    )
