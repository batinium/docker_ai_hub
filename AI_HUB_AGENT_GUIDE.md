# AI Hub Service Guide (Agentic Clients)

Use this file when integrating external apps or agents with the AI Hub gateway.
It is intended for LLM-powered clients that need to discover endpoints, auth,
and example payloads quickly.

## Base URLs

- Tailscale (recommended, stable): `http://100.120.207.64:8080`
- LAN (if routed on the local network): `http://192.168.1.103:8080`

Use the Tailscale URL for remote agents and long-lived client configs. The LAN
address can change with DHCP and should be treated as local-network only.

## Auth

If `GATEWAY_API_KEYS` is set in `.env`, add `X-API-Key: <your-key>` to every request.
Missing/invalid key returns `401` with JSON: `{"error":"Invalid or missing API key"}`.

## Gateway Routes (Overview)

All routes below are accessed via the gateway base URL.

- llama.cpp (Docker, OpenAI-compatible): `/llama/v1/...`
- LM Studio (host app, OpenAI-compatible): `/lmstudio/v1/...`
- Kokoro TTS: `/kokoro/v1/audio/speech`
- Faster Whisper STT: `/stt/v1/audio/transcriptions`
- OpenRouter (optional): `/openrouter/v1/...`

## Current LLM Defaults

Use llama.cpp for the Docker-hosted local LLM path.

- Base route: `/llama/v1/...`
- Deployed request model: `qwen2.5-7b-instruct`
- Backing file: `/models/lmstudio-community/Qwen2.5-7B-Instruct-GGUF/Qwen2.5-7B-Instruct-Q4_K_M.gguf`
- Container: `llama_cpp`
- Direct host port: none; access it only through the gateway.

LM Studio remains available as a gateway route, but it depends on the separate
host LM Studio app being open and reachable from Docker at `LMSTUDIO_HOST`.

## LLM (llama.cpp, OpenAI-compatible)

- Models: `GET /llama/v1/models`
- Chat: `POST /llama/v1/chat/completions`
- Completions: `POST /llama/v1/completions`
- Embeddings: `POST /llama/v1/embeddings`

Notes:
- This is the preferred local LLM endpoint for Docker-only operation.
- The generic default alias in compose is `local-gguf`, but this deployment uses `qwen2.5-7b-instruct`.
- `LLAMA_CPP_MODELS_DIR` mounts the host model root into the container as `/models`.
- `LLAMA_CPP_N_GPU_LAYERS=999` asks llama.cpp to offload all possible layers to GPU.
- Typical errors: `401` (missing/invalid API key), `502` (container not running, model path wrong, or GPU runtime unavailable).

Models example:
```bash
curl http://100.120.207.64:8080/llama/v1/models \
  -H "X-API-Key: <your-key>"
```

Chat example:
```bash
curl http://100.120.207.64:8080/llama/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"model":"qwen2.5-7b-instruct","messages":[{"role":"user","content":"Summarize this in one sentence."}]}'
```

Completions example:
```bash
curl http://100.120.207.64:8080/llama/v1/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"model":"qwen2.5-7b-instruct","prompt":"Write a short haiku about rain."}'
```

## LLM (LM Studio, OpenAI-compatible)

- Models: `GET /lmstudio/v1/models`
- Responses: `POST /lmstudio/v1/responses`
- Chat: `POST /lmstudio/v1/chat/completions`
- Completions: `POST /lmstudio/v1/completions`
- Embeddings: `POST /lmstudio/v1/embeddings`

Notes:
- `model` must match an ID from `GET /lmstudio/v1/models`.
- This route proxies to the host LM Studio app, not a Docker container.
- `LMSTUDIO_HOST` should point to the address Docker can use to reach LM Studio, usually `host.docker.internal` on Docker Desktop.
- Do not set `LMSTUDIO_HOST` to the public gateway IP or Tailscale IP; that loops nginx back to itself.
- Typical errors: `401` (missing/invalid API key), `502` (LM Studio app not running, server disabled, wrong host, or wrong port).

Example (preferred, `responses`):
```bash
curl http://100.120.207.64:8080/lmstudio/v1/responses \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"model":"google/gemma-3-4b","input":"Hello"}'
```

Chat example:
```bash
curl http://100.120.207.64:8080/lmstudio/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"model":"google/gemma-3-4b","messages":[{"role":"user","content":"Summarize this in one sentence."}]}'
```

Completions example:
```bash
curl http://100.120.207.64:8080/lmstudio/v1/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"model":"google/gemma-3-4b","prompt":"Write a short haiku about rain."}'
```

Embeddings example:
```bash
curl http://100.120.207.64:8080/lmstudio/v1/embeddings \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"model":"text-embedding-nomic-embed-text-v1.5","input":"hello world"}'
```

Structured Output (JSON Schema) example:
*(Supported natively by LM Studio via standard OpenAI API format)*

```bash
curl http://100.120.207.64:8080/lmstudio/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{
    "model": "qwen2.5-3b-instruct",
    "messages": [{"role": "user", "content": "Extract details: Name is Alice, age is 25."}],
    "response_format": {
      "type": "json_schema",
      "json_schema": {
        "name": "user_details",
        "schema": {
          "type": "object",
          "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"}
          },
          "required": ["name", "age"]
        }
      }
    }
  }'
```

Tool Calling example:
*(Supported natively by LM Studio via standard OpenAI API format)*

```bash
curl http://100.120.207.64:8080/lmstudio/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{
    "model": "qwen2.5-3b-instruct",
    "messages": [{"role": "user", "content": "What is the weather in Paris?"}],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_weather",
          "description": "Get current weather in a given location",
          "parameters": {
            "type": "object",
            "properties": {
              "location": { "type": "string", "description": "The city name" }
            },
            "required": ["location"]
          }
        }
      }
    ],
    "tool_choice": "auto"
  }'
```

## TTS (Kokoro)

- Speech: `POST /kokoro/v1/audio/speech`

Notes:
- Returns audio bytes (e.g., MP3). Use `--output` to save.
- Runs with `ghcr.io/remsky/kokoro-fastapi-cpu:latest`.
- The proxy implements a 1-hour cache based on exact JSON payloads. If you generate the exact same text/voice configuration, nginx can return the stored MP3 without calling Kokoro again.
- Rate limit: 20 requests/minute, bursting up to 10.
- Common voices include `af_bella`, `af_heart` (list depends on installed packs).

Example:
```bash
curl http://100.120.207.64:8080/kokoro/v1/audio/speech \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"model":"kokoro","input":"Hello","voice":"af_bella","response_format":"mp3"}' \
  --output hello.mp3
```

## STT (Faster Whisper)

- Transcriptions: `POST /stt/v1/audio/transcriptions`

Notes:
- Use multipart upload with `file=@...`.
- The gateway route points to `faster_whisper_rest`, configured with `DEVICE=cuda` and `COMPUTE_TYPE=float16`.
- Rate limit: 5 requests/minute, max 2 concurrent connections.
- You can optionally force a specific language via `-F "language=tr"` or `-F "language=en"`. This is highly recommended to improve transcription accuracy and speed.
- Returns JSON with a `text` field.

Example:
```bash
curl http://100.120.207.64:8080/stt/v1/audio/transcriptions \
  -H "X-API-Key: <your-key>" \
  -F "file=@sample.wav" \
  -F "language=tr"
```

## OpenRouter (Optional)

Set `OPENROUTER_API_KEY` in `.env` to enable.

- Chat: `POST /openrouter/v1/chat/completions`

Notes:
- If not configured, the gateway will return `502` upstream errors.

Example:
```bash
curl http://100.120.207.64:8080/openrouter/v1/chat/completions \
  -H "X-API-Key: <your-key>" \
  -H "Content-Type: application/json" \
  -d '{"model":"openrouter/auto","messages":[{"role":"user","content":"Hello"}]}'
```

## Direct (Non-Gateway) Access (Security Note)

**Important:** For security reasons, direct host port exposure for backend containers is closed. Client traffic should pass through the gateway on port `8080`, where optional `X-API-Key` auth and proxy limits are applied before requests reach backend services.

- LM Studio (local Windows app): `http://<HOST-IP>:1234/v1/...`
- llama.cpp: no direct host port is published by Compose; use `/llama/v1/...` through the gateway.

## LLM Client Quick Start (Prompt Snippet)

Use this snippet to configure LLM agents or external apps:

```
Base URL: http://100.120.207.64:8080
Auth header: X-API-Key: <your-key>
Default local LLM model: qwen2.5-7b-instruct
Endpoints:
  - llama.cpp Models: /llama/v1/models
  - llama.cpp Chat: /llama/v1/chat/completions
  - llama.cpp Completions: /llama/v1/completions
  - llama.cpp Embeddings: /llama/v1/embeddings
  - Responses: /lmstudio/v1/responses
  - Chat: /lmstudio/v1/chat/completions
  - Completions: /lmstudio/v1/completions
  - Embeddings: /lmstudio/v1/embeddings
  - TTS: /kokoro/v1/audio/speech
  - STT: /stt/v1/audio/transcriptions
Behavior:
  - If 401: missing/invalid key.
  - If 502: upstream not running or unreachable (retry/backoff).
```

## Diagnostics

- Full gateway check:
  `python scripts/connectivity_check.py --mode client --ip 100.120.207.64 --gateway-port 8080 --llama-model qwen2.5-7b-instruct --lmstudio-model "" --openrouter-model ""`
- Container status:
  `docker compose ps llama_cpp`
- llama.cpp health path:
  `GET /llama/health`
- llama.cpp models path:
  `GET /llama/v1/models`
- Kokoro docs: `GET /kokoro/docs`
- STT docs: `GET /stt/docs`
- Gateway errors:
  - `401` = missing/invalid API key
  - `502` = upstream not running/reachable
  - timeout = backend accepted the request but did not finish before the client/proxy timeout
