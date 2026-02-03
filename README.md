# claude-code-openai-proxy

[English](#english) | [中文](#中文)

---

<a name="english"></a>
## English

🔌 **OpenAI-compatible API proxy for Claude Code CLI** - Use Claude Code as a backend for OpenClaw, Cursor, and other AI tools that support OpenAI API.

### Why This Project?

Claude Code CLI is a powerful AI coding assistant, but it only works in the terminal. This proxy exposes it as an OpenAI-compatible API, enabling you to:

- Use **Claude Code** as the backend for **[OpenClaw](https://openclaw.ai)**
- Connect **Cursor**, **Continue**, or other AI coding tools to Claude Code
- Build custom applications leveraging Claude Code's agentic capabilities
- Access Claude Code remotely via HTTP API

### Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│                 │     │                      │     │                 │
│  OpenClaw       │     │  claude-code-        │     │  Claude Code    │
│  Cursor         │────▶│  openai-proxy        │────▶│  CLI            │
│  Custom Apps    │     │                      │     │                 │
│                 │     │  localhost:18880     │     │  (Anthropic)    │
└─────────────────┘     └──────────────────────┘     └─────────────────┘
        │                         │                         │
   OpenAI API              FastAPI Server              Subprocess

   POST /v1/chat/          • Request format            • --dangerously-
   completions               translation                 skip-permissions
                           • Streaming SSE             • Agentic mode
                           • Session isolation         • Tool execution
```

### How It Works

```
┌────────────────────────────────────────────────────────────────────┐
│                        Request Flow                                │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  1. Client Request (OpenAI format)                                 │
│     POST /v1/chat/completions                                      │
│     {                                                              │
│       "messages": [                                                │
│         {"role": "system", "content": "..."},                      │
│         {"role": "user", "content": "Write hello world"}           │
│       ]                                                            │
│     }                                                              │
│                          ▼                                         │
│  2. Message Merging                                                │
│     • Extract system prompt                                        │
│     • Combine user/assistant messages                              │
│     • Support content blocks format (OpenClaw)                     │
│                          ▼                                         │
│  3. Claude Code CLI Execution                                      │
│     claude -p --dangerously-skip-permissions \                     │
│            --output-format stream-json \                           │
│            --append-system-prompt "..." \                          │
│            "user prompt"                                           │
│                          ▼                                         │
│  4. Response Translation                                           │
│     • Parse stream-json output                                     │
│     • Extract text from assistant messages                         │
│     • Convert to OpenAI SSE format                                 │
│                          ▼                                         │
│  5. Client Response (OpenAI format)                                │
│     data: {"choices":[{"delta":{"content":"Hello..."}}]}           │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### Features

- ✅ OpenAI Chat Completions API compatible
- ✅ **Tool Calling (Function Calling) support** - Full OpenAI-compatible tool use
- ✅ Streaming support (Server-Sent Events)
- ✅ System prompt passthrough
- ✅ Multi-turn conversation support (via client-side history)
- ✅ Content blocks format support (for OpenClaw)
- ✅ macOS LaunchAgent for auto-start
- ✅ Optional Bearer token authentication

### Why This Over Official `claude-max-api`?

| Feature | This Proxy | claude-max-api |
|---------|------------|----------------|
| **Tool Calling** | ✅ Full support | ❌ Not supported |
| Content Blocks Format | ✅ Supported | ❌ Returns `[object Object]` |
| Streaming | ✅ Works correctly | ⚠️ Issues reported |
| OpenClaw Integration | ✅ Tested & verified | ⚠️ Compatibility issues |

**Tool calling is critical** for AI assistants like OpenClaw that need to browse the web, control your screen, read files, and more. Without tool calling, these capabilities don't work.

### Requirements

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- macOS (for LaunchAgent) or Linux

### Quick Start

```bash
# Clone the repository
git clone https://github.com/user/claude-code-openai-proxy.git
cd claude-code-openai-proxy

# Option 1: Use the startup script (recommended)
./run.sh

# Option 2: Manual setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_BIN` | Auto-detect | Path to Claude Code binary |
| `PROXY_PORT` | `18880` | API server port |
| `PROXY_HOST` | `0.0.0.0` | API server host |
| `CLAUDE_PROXY_TOKEN` | (none) | Optional Bearer token for auth |
| `CLAUDE_MAX_TURNS` | `10` | Max agentic turns per request |
| `CLAUDE_TIMEOUT` | `300` | Request timeout in seconds |
| `MODEL_NAME` | `claude-code` | Model name in API responses |

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Health check |
| GET | `/v1/models` | List available models |
| POST | `/v1/chat/completions` | Chat completions (OpenAI-compatible) |
| POST | `/chat/completions` | Alias without /v1 prefix |

### Usage Examples

#### cURL

```bash
# Non-streaming
curl http://localhost:18880/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-code",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# Streaming
curl http://localhost:18880/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-code",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": true
  }'
```

#### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:18880/v1",
    api_key="not-needed"  # or your CLAUDE_PROXY_TOKEN
)

response = client.chat.completions.create(
    model="claude-code",
    messages=[{"role": "user", "content": "Write a hello world in Python"}]
)
print(response.choices[0].message.content)
```

#### Tool Calling Example

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:18880/v1", api_key="not-needed")

# Define tools
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get weather for a city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"]
        }
    }
}]

# Request with tools
response = client.chat.completions.create(
    model="claude-code",
    messages=[{"role": "user", "content": "What's the weather in Tokyo?"}],
    tools=tools
)

# Check for tool calls
if response.choices[0].message.tool_calls:
    for tool_call in response.choices[0].message.tool_calls:
        print(f"Tool: {tool_call.function.name}")
        print(f"Args: {tool_call.function.arguments}")
```

#### OpenClaw Integration

Add to your OpenClaw config (`~/.openclaw/openclaw.json`):

```json
{
  "models": {
    "providers": {
      "claude-code": {
        "baseUrl": "http://127.0.0.1:18880/v1",
        "apiKey": "claude-code",
        "api": "openai-completions",
        "models": [
          {
            "id": "claude-code",
            "name": "Claude Code Proxy (local)",
            "reasoning": false,
            "input": ["text"],
            "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 },
            "contextWindow": 200000,
            "maxTokens": 8192
          }
        ]
      }
    }
  }
}
```

Then set it as default:

```bash
openclaw models set claude-code/claude-code
launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
```

### Service Management (macOS)

```bash
# Install as auto-start service
./install_service.sh

# Check status
launchctl list | grep claude-code

# View logs
tail -f logs/stdout.log
tail -f logs/stderr.log

# Restart service
launchctl kickstart -k gui/$(id -u)/com.claude-code.openai-proxy

# Uninstall service
./uninstall_service.sh
```

### Limitations

- No persistent sessions (each request is stateless)
- Claude Code CLI must be pre-authenticated
- Tool calling mode does not support streaming (JSON schema requires full output)

### License

MIT

---

<a name="中文"></a>
## 中文

🔌 **Claude Code CLI 的 OpenAI 兼容 API 代理** - 让 OpenClaw、Cursor 等支持 OpenAI API 的 AI 工具使用 Claude Code 作为后端。

### 为什么需要这个项目？

Claude Code CLI 是一个强大的 AI 编程助手，但它只能在终端使用。这个代理将它暴露为 OpenAI 兼容的 API，让你可以：

- 用 **Claude Code** 作为 **[OpenClaw](https://openclaw.ai)** 的后端
- 将 **Cursor**、**Continue** 等 AI 编程工具连接到 Claude Code
- 基于 Claude Code 的 Agent 能力构建自定义应用
- 通过 HTTP API 远程访问 Claude Code

### 架构设计

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│                 │     │                      │     │                 │
│  OpenClaw       │     │  claude-code-        │     │  Claude Code    │
│  Cursor         │────▶│  openai-proxy        │────▶│  CLI            │
│  自定义应用      │     │                      │     │                 │
│                 │     │  localhost:18880     │     │  (Anthropic)    │
└─────────────────┘     └──────────────────────┘     └─────────────────┘
        │                         │                         │
   OpenAI API              FastAPI 服务器                子进程调用

   POST /v1/chat/          • 请求格式转换               • --dangerously-
   completions             • SSE 流式响应                 skip-permissions
                           • 会话隔离                   • Agent 模式
                                                        • 工具执行
```

### 工作原理

```
┌────────────────────────────────────────────────────────────────────┐
│                          请求处理流程                               │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  1. 客户端请求 (OpenAI 格式)                                        │
│     POST /v1/chat/completions                                      │
│     {                                                              │
│       "messages": [                                                │
│         {"role": "system", "content": "..."},                      │
│         {"role": "user", "content": "写个 Hello World"}             │
│       ]                                                            │
│     }                                                              │
│                          ▼                                         │
│  2. 消息合并                                                        │
│     • 提取 system prompt                                           │
│     • 合并 user/assistant 消息                                      │
│     • 支持 content blocks 格式 (OpenClaw 使用)                      │
│                          ▼                                         │
│  3. Claude Code CLI 执行                                           │
│     claude -p --dangerously-skip-permissions \                     │
│            --output-format stream-json \                           │
│            --append-system-prompt "..." \                          │
│            "用户提示词"                                              │
│                          ▼                                         │
│  4. 响应转换                                                        │
│     • 解析 stream-json 输出                                         │
│     • 从 assistant 消息中提取文本                                    │
│     • 转换为 OpenAI SSE 格式                                        │
│                          ▼                                         │
│  5. 客户端响应 (OpenAI 格式)                                        │
│     data: {"choices":[{"delta":{"content":"Hello..."}}]}           │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### 功能特性

- ✅ 兼容 OpenAI Chat Completions API
- ✅ **支持 Tool Calling（函数调用）** - 完全兼容 OpenAI 工具调用格式
- ✅ 支持流式响应 (Server-Sent Events)
- ✅ 支持 System Prompt 透传
- ✅ 支持多轮对话（通过客户端历史记录）
- ✅ 支持 Content Blocks 格式（OpenClaw 使用）
- ✅ macOS LaunchAgent 开机自启
- ✅ 可选的 Bearer Token 认证

### 为什么选择这个而不是官方 `claude-max-api`？

| 特性 | 本代理 | claude-max-api |
|------|--------|----------------|
| **Tool Calling** | ✅ 完整支持 | ❌ 不支持 |
| Content Blocks 格式 | ✅ 支持 | ❌ 返回 `[object Object]` |
| 流式响应 | ✅ 正常工作 | ⚠️ 有问题 |
| OpenClaw 集成 | ✅ 已测试验证 | ⚠️ 兼容性问题 |

**Tool calling 至关重要** - OpenClaw 等 AI 助手需要浏览网页、控制屏幕、读取文件等能力。没有 Tool Calling，这些功能都无法使用。

### 环境要求

- Python 3.10+
- 已安装并登录的 [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)
- macOS（用于 LaunchAgent）或 Linux

### 快速开始

```bash
# 克隆仓库
git clone https://github.com/user/claude-code-openai-proxy.git
cd claude-code-openai-proxy

# 方式一：使用启动脚本（推荐）
./run.sh

# 方式二：手动设置
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

### 配置项

环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CLAUDE_BIN` | 自动检测 | Claude Code 二进制文件路径 |
| `PROXY_PORT` | `18880` | API 服务端口 |
| `PROXY_HOST` | `0.0.0.0` | API 服务主机 |
| `CLAUDE_PROXY_TOKEN` | (无) | 可选的 Bearer Token 认证 |
| `CLAUDE_MAX_TURNS` | `10` | 每个请求最大 Agent 轮次 |
| `CLAUDE_TIMEOUT` | `300` | 请求超时时间（秒） |
| `MODEL_NAME` | `claude-code` | API 响应中的模型名称 |

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 健康检查 |
| GET | `/v1/models` | 列出可用模型 |
| POST | `/v1/chat/completions` | Chat Completions（OpenAI 兼容）|
| POST | `/chat/completions` | 无 /v1 前缀的别名 |

### 使用示例

#### cURL

```bash
# 非流式
curl http://localhost:18880/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-code",
    "messages": [{"role": "user", "content": "你好！"}]
  }'

# 流式
curl http://localhost:18880/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-code",
    "messages": [{"role": "user", "content": "你好！"}],
    "stream": true
  }'
```

#### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:18880/v1",
    api_key="not-needed"  # 或者你的 CLAUDE_PROXY_TOKEN
)

response = client.chat.completions.create(
    model="claude-code",
    messages=[{"role": "user", "content": "用 Python 写一个 Hello World"}]
)
print(response.choices[0].message.content)
```

#### Tool Calling 示例

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:18880/v1", api_key="not-needed")

# 定义工具
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "获取城市天气",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"]
        }
    }
}]

# 带工具的请求
response = client.chat.completions.create(
    model="claude-code",
    messages=[{"role": "user", "content": "东京天气怎么样？"}],
    tools=tools
)

# 检查工具调用
if response.choices[0].message.tool_calls:
    for tool_call in response.choices[0].message.tool_calls:
        print(f"工具: {tool_call.function.name}")
        print(f"参数: {tool_call.function.arguments}")
```

#### OpenClaw 集成

在 OpenClaw 配置文件中添加 (`~/.openclaw/openclaw.json`):

```json
{
  "models": {
    "providers": {
      "claude-code": {
        "baseUrl": "http://127.0.0.1:18880/v1",
        "apiKey": "claude-code",
        "api": "openai-completions",
        "models": [
          {
            "id": "claude-code",
            "name": "Claude Code Proxy (local)",
            "reasoning": false,
            "input": ["text"],
            "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 },
            "contextWindow": 200000,
            "maxTokens": 8192
          }
        ]
      }
    }
  }
}
```

然后设为默认：

```bash
openclaw models set claude-code/claude-code
launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
```

### 服务管理 (macOS)

```bash
# 安装为开机自启服务
./install_service.sh

# 检查状态
launchctl list | grep claude-code

# 查看日志
tail -f logs/stdout.log
tail -f logs/stderr.log

# 重启服务
launchctl kickstart -k gui/$(id -u)/com.claude-code.openai-proxy

# 卸载服务
./uninstall_service.sh
```

### 局限性

- 无持久化会话（每个请求独立、无状态）
- Claude Code CLI 需要预先认证
- Tool Calling 模式不支持流式响应（JSON Schema 需要完整输出）

### 开源协议

MIT

---

## Contributing

Issues and PRs are welcome!

## Related Projects

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) - Anthropic's official AI coding assistant
- [OpenClaw](https://openclaw.ai) - Personal AI assistant platform
