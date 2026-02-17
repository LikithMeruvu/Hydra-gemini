<div align="center">
  <img src="hydra/api/static/logo_complete.png" alt="Hydra Logo" height="100"/>
  <br/><br/>

  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
  [![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
  [![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
  [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

  <h3>Unlimited Free-Tier Gemini API Gateway</h3>
  <p>Route requests to 20+ free keys with automatic failover, rate-limit rotation, and full OpenAI compatibility.</p>
</div>

---

## 📖 Table of Contents
- [✨ Features](#-features)
- [🚀 Quick Start](#-quick-start)
- [📦 Installation](#-installation)
- [🔐 Authentication](#-authentication)
- [🛠️ Integration (SDKs & IDEs)](#️-integration-sdks--ides)
- [🔌 API Reference](#-api-reference)
- [🤖 Advanced Features](#-advanced-features)
- [🛡️ Admin & Tunneling](#️-admin--tunneling)
- [⚠️ Troubleshooting](#️-troubleshooting)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)

---

## ✨ Features
- **Unlimited Usage**: Aggregate multiple free-tier keys (15 RPM each) into a single high-throughput endpoint.
- **Failover & Rotation**: Automatically detects rate limits (`429`) and switches to the next healthy key instantly.
- **OpenAI Compatible**: Drop-in replacement for `openai-python`, `openai-node`, and tools like Cursor/VSCode.
- **Multi-Model Support**: Access `gemini-2.5-flash`, `gemini-2.5-pro`, and reasoning models like `gemini-2.0-flash-thinking`.
- **Advanced Capabilities**: Supports **Vision** (Images), **Function Calling** (Tool Use), and **Web Search**.
- **Admin Dashboard**: Visual interface to monitor key health, usage stats, and manage tokens.
- **Secure Tunneling**: Built-in Cloudflare Tunnel to expose your localhost gateway to the internet safely.

---

## 🚀 Quick Start
Get up and running in 2 minutes.

### 1. Install
```bash
pip install -e .
```

### 2. Configure Keys
Create `keys.json` with your Google AI Studio keys:
```json
[
  {"email": "account1@gmail.com", "api_key": "AIzaSy...", "project_id": "proj-1"},
  {"email": "account2@gmail.com", "api_key": "AIzaSy...", "project_id": "proj-2"}
]
```

### 3. Run
```bash
# Verify setup
hydra setup --file keys.json

# Start Gateway
hydra gateway
```
Your API is now live at `http://localhost:8000/v1`.

---

## 📦 Installation
Requirements: Python 3.10+ and Redis.

### 1. Redis (Required)
Hydra uses Redis for high-speed state management and rate limiting.
- **Windows**: Install via WSL or use [Memurai](https://www.memurai.com/).
- **Mac**: `brew install redis`
- **Linux**: `apt install redis-server`

### 2. Install Hydra
```bash
git clone https://github.com/LikithMeruvu/Hydra-gemini.git
cd Hydra-gemini
pip install -e .
```

---

## 🔐 Authentication
By default, the API is open if no tokens are configured. To secure it:

```bash
# Generate a token
hydra tokens create --name my-app
# Output: hydra-sk-12345...
```

Send this token in the header:
`Authorization: Bearer hydra-sk-12345...`

---

## 🛠️ Integration (SDKs & IDEs)

### Python (OpenAI SDK)
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="hydra-sk-..."
)

response = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

### Node.js
```javascript
import OpenAI from 'openai';

const client = new OpenAI({
    baseURL: 'http://localhost:8000/v1',
    apiKey: 'hydra-sk-...'
});
```

### Cursor / VS Code (Cline)
1. Go to Settings > Models.
2. Add **OpenAI** (or generic) endpoint.
3. Base URL: `http://localhost:8000/v1`.
4. API Key: Your Hydra token.
5. Model Name: `gemini-2.5-flash`.

---

## 🔌 API Reference

### Chat Completions
`POST /v1/chat/completions`
- **Streaming**: Supported (`stream=True`).
- **Models**: `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.0-flash-thinking-exp`.

### List Models
`GET /v1/models`
Returns all available Gemini models detectable by your keys.

---

## 🤖 Advanced Features

### 👁️ Vision (Image Input)
Send images as Base64 or URLs.
```python
response = client.chat.completions.create(
    model="gemini-2.5-pro",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What is in this image?"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
            ]
        }
    ]
)
```

### ⚙️ Function Calling (Tool Use)
Hydra translates OpenAI tool definitions into Gemini's format.
```python
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}
    }
}]
# Call with tools=tools using standard OpenAI SDK
```

### 🌍 Web Search (Grounding)
Enable Google Search grounding by adding a special tool:
```json
"tools": [{"google_search": {}}]
```

---

## 🛡️ Admin & Tunneling

### The Dashboard
Visit `http://localhost:8000/dashboard` to see:
- Real-time Request/Minute (RPM) graph.
- Health status of every API key.
- Token management UI.

### Public Exposure (Tunneling)
Want to use Hydra from a Vercel app or a different network?
```bash
hydra gateway --expose
```
This automatically downloads `cloudflared` and gives you a secure `https://...` URL.

---

## ⚠️ Troubleshooting

| Error | Meaning | Fix |
|---|---|---|
| `429` | All keys exhausted | Add more keys to `keys.json` or wait 60s. |
| `401` | Unauthorized | Check your `Authorization: Bearer` header. |
| `503` | Gateway Error | Check your internet connection (Google API unreachable). |

**Logs**: Run `hydra logs` to see detailed error traces.

---

## 🤝 Contributing
1. Fork the repo.
2. Create a branch (`git checkout -b feature/amazing`).
3. Commit changes (`git commit -m 'Add amazing feature'`).
4. Push (`git push origin feature/amazing`).
5. Open a Pull Request.

---

## 📄 License
MIT License. See [LICENSE](LICENSE) for details.
