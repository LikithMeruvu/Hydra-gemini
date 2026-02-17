<div align="center">

<div align="center">
  <img src="hydra/api/static/logo_complete.png" alt="Hydra Logo" height="80"/>
  <br/><br/>

  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
</div>

---

## 🎯 What Is Hydra?

Hydra lets you pool **20+ free-tier Gemini API keys** behind a single **OpenAI-compatible endpoint**. It intelligently routes requests, tracks rate limits, and automatically falls back to alternate keys/models when limits are hit.

**Result:** ~27,800 free requests/day instead of ~250.

### Supported Models (Free Tier)

| Model | RPM | RPD | TPM |
|---|---|---|---|
| Gemini 3 Flash Preview | 5 | ~50 | 250K |
| Gemini 2.5 Pro | 5 | 100 | 250K |
| Gemini 2.5 Flash | 10 | 250 | 250K |
| Gemini 2.5 Flash-Lite | 15 | 1,000 | 250K |

> **Key insight:** Rate limits are per *Google Cloud Project*, not per API key. 20 projects = 20× the capacity.

---

## 🚀 Quick Start

### 1. Install

```bash
pip install -e .
```

### 2. Start Redis

```bash
# Docker
docker run -d -p 6379:6379 redis:7-alpine
```

### 3. Create Key File

Create `keys.json`:
```json
[
  {"email": "user1@gmail.com", "api_key": "AIzaSyA...", "project_id": "projects/123"},
  {"email": "user2@gmail.com", "api_key": "AIzaSyB...", "project_id": "projects/456"}
]
```

### 4. Setup & Run

```bash
hydra setup --file keys.json
hydra gateway
```

Your API is now running at `http://localhost:8000`.

---

## �️ Installation & Setup

### Prerequisites
1.  **Python 3.10+** (Required)
2.  **Redis Server** (Required for state management)
    *   **Windows**: Install via WSL or use [Memurai](https://www.memurai.com/).
    *   **Mac/Linux**: `brew install redis` / `apt install redis-server`.

### Quick Start (GitHub)

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/trulyunlimitedgemini/hydra.git
    cd hydra
    ```

2.  **Install Application**
    ```bash
    pip install -e .
    ```

3.  **Configure API Keys**
    Create a `keys.json` file (see `examples/keys.json`) or use the setup wizard:
    ```bash
    hydra setup --file keys.json
    ```

4.  **Start the Gateway**
    ```bash
    # Local only
    hydra gateway

    # Expose to the internet (Public URL)
    hydra gateway --expose
    ```

## 🏗️ Architecture: How it Works

Hydra sits between your application (Cursor, LangChain, etc.) and Google's Gemini API.

1.  **The "Heads" (API Keys)**: You provide multiple free-tier keys. Hydra monitors their rate limits in Redis.
2.  **The Gateway**: Routes incoming OpenAI-compatible requests to the healthiest key.
3.  **The Tunnel (Optional)**: Using `hydra gateway --expose`, it launches a lightweight `cloudflared` tunnel to give you a public `https://...` URL. This allows you to connect remote tools (like Vercel apps or mobile agents) to your local Hydra instance without firewall changes.

---

## �🔑 Access Tokens

Use **tokens** to secure your API when exposing it globally or sharing it.

```bash
# Create a token
hydra tokens create --name cursor-ide
# Output: hydra-abcdef123...

# List all tokens
hydra tokens

# Watch usage in real-time
hydra tokens watch
```

---

## 🌍 Global Exposure

Expose your local gateway to the internet securely using Cloudflare Tunnel.

```bash
hydra gateway --expose
```

This will:
1. Start the gateway
2. Download and start `cloudflared`
3. Generate a temporary admin token
4. Give you a public URL (e.g., `https://random-name.trycloudflare.com`)

---

## 🔌 API Usage

Hydra is fully **OpenAI-compatible**. Use it with any standard client.

### Curl
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "model": "gemini-2.5-flash",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Python (OpenAI SDK)
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="YOUR_TOKEN"
)

response = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True
)
for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

### IDE Integration (Cursor, VS Code, etc.)

Just set the **Base URL** to `http://localhost:8000/v1` (or your public URL) and use your Hydra token as the API Key.

---

## 🤖 Expert Tool Use (Function Calling)

Hydra creates a seamless bridge between OpenAI's **Tool Use** format and Gemini's Function Calling. You send OpenAI-style tool definitions, and Hydra handles the conversion, execution, and response mapping.

### Python Example
```python
tools = [{
    "type": "function",
    "function": {
        "name": "get_stock_price",
        "description": "Get current stock price",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol (e.g. AAPL)"}
            },
            "required": ["symbol"]
        }
    }
}]

response = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=[{"role": "user", "content": "What's Apple's stock price?"}],
    tools=tools,
    tool_choice="auto"
)

tool_call = response.choices[0].message.tool_calls[0]
print(tool_call.function.name)      # get_stock_price
print(tool_call.function.arguments) # {"symbol": "AAPL"}
```

**Supported Features:**
- `tools` (list of function definitions)
- `tool_choice` ("auto", "none", or specific function)
- Parallel function calling (handled by Gemini 2.5 models)
- Automatic ID generation compatible with OpenAI SDKs

---

## 🛡️ Security

| Endpoint | Access | Auth Required |
|---|---|---|
| `/v1/*` | Public | ✅ Bearer Token |
| `/docs` | Public | ❌ None |
| `/health` | Public | ❌ None |
| `/admin/*` | **Localhost Only** | ❌ None (IP restricted) |
| `/` (Dashboard) | **Localhost Only** | ❌ None (IP restricted) |

---

## 📄 License

MIT — see [LICENSE](LICENSE).
