#!/usr/bin/env python3
"""
Claude Code OpenAI-Compatible Proxy Server

This server wraps Claude Code CLI as an OpenAI-compatible API endpoint.
It exposes /v1/chat/completions and /v1/models endpoints.

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

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from config import config
from models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
    ChatMessage,
    Usage,
    ModelInfo,
    ModelListResponse,
)
from claude_executor import execute_claude_code

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Claude Code OpenAI Proxy",
    description="OpenAI-compatible API proxy for Claude Code CLI",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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
        "version": "1.0.0",
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
    Wraps Claude Code CLI with full permissions.
    """
    if not verify_token(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")

    request_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    logger.info(f"Request {request_id}: model={request.model}, messages={len(request.messages)}, stream={request.stream}")
    logger.info(f"Request {request_id} messages: {[m.model_dump() for m in request.messages]}")

    if request.stream:
        return EventSourceResponse(
            _stream_response(request_id, request),
            media_type="text/event-stream",
        )
    else:
        return await _blocking_response(request_id, request)


async def _blocking_response(request_id: str, request: ChatCompletionRequest) -> ChatCompletionResponse:
    """Generate a blocking (non-streaming) response."""
    content_parts = []

    async for chunk in execute_claude_code(request.messages, stream=False):
        content_parts.append(chunk)

    full_content = "".join(content_parts)

    # Estimate token counts (rough approximation)
    prompt_tokens = sum(len(m.content.split()) for m in request.messages) * 2
    completion_tokens = len(full_content.split()) * 2

    return ChatCompletionResponse(
        id=request_id,
        model=request.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatMessage(
                    role="assistant",
                    content=full_content,
                ),
                finish_reason="stop",
            )
        ],
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
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


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Claude Code OpenAI Proxy on {config.host}:{config.port}")
    logger.info(f"Claude binary: {config.claude_bin}")
    logger.info(f"Model name: {config.model_name}")
    logger.info(f"Auth required: {bool(config.proxy_token)}")

    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="info",
    )
