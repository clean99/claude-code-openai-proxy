from typing import List, Optional, Union, Literal, Any
from pydantic import BaseModel, Field, field_validator, model_validator
import time


class ContentBlock(BaseModel):
    """Content block for multimodal messages."""
    type: str
    text: Optional[str] = None
    image_url: Optional[dict] = None


# Tool-related models
class ToolFunctionParameters(BaseModel):
    """Parameters schema for a tool function."""
    type: str = "object"
    properties: Optional[dict] = None
    required: Optional[List[str]] = None

    class Config:
        extra = "allow"


class ToolFunction(BaseModel):
    """Function definition for a tool."""
    name: str
    description: Optional[str] = None
    parameters: Optional[dict] = None


class Tool(BaseModel):
    """Tool definition in OpenAI format."""
    type: str = "function"
    function: ToolFunction


class FunctionCall(BaseModel):
    """Function call in assistant's tool_calls."""
    name: str
    arguments: str  # JSON string


class ToolCall(BaseModel):
    """Tool call made by the assistant."""
    id: str
    type: str = "function"
    function: FunctionCall


class ChatMessage(BaseModel):
    """Chat message supporting string, content blocks, tool calls, and tool results."""
    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[Union[str, List[Any]]] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None  # For tool result messages
    name: Optional[str] = None  # Tool name for tool result messages

    @field_validator("content", mode="before")
    @classmethod
    def normalize_content(cls, v):
        """Convert content blocks array to string."""
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if isinstance(v, list):
            # Extract text from content blocks
            texts = []
            for block in v:
                if isinstance(block, dict):
                    if block.get("type") == "text" and "text" in block:
                        texts.append(block["text"])
                    elif "text" in block:
                        texts.append(block["text"])
                elif isinstance(block, str):
                    texts.append(block)
            return "\n".join(texts) if texts else ""
        return str(v) if v else ""

    def get_content_str(self) -> str:
        """Get content as string."""
        if isinstance(self.content, str):
            return self.content
        return ""


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    stop: Optional[Union[str, List[str]]] = None
    user: Optional[str] = None
    # Tool calling support
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[Union[str, dict]] = None


class ResponseMessage(BaseModel):
    """Message in completion response, may include tool_calls."""
    role: str = "assistant"
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None


class ChatCompletionChoice(BaseModel):
    index: int
    message: ResponseMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChoice]
    usage: Usage


class ChatCompletionChunkDelta(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None
    tool_calls: Optional[List[dict]] = None


class ChatCompletionChunkChoice(BaseModel):
    index: int
    delta: ChatCompletionChunkDelta
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChunkChoice]


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "claude-code-proxy"


class ModelListResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]
