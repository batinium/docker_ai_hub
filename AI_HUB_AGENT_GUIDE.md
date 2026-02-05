# AI Hub Service Guide (Agentic Clients)

Use this file when integrating external apps or agents with the AI Hub gateway.
It is intended for LLM-powered clients that need to discover endpoints, auth,
and example payloads quickly.

## Base URLs

- Tailscale (recommended, stable): `http://100.120.207.64:8080`
- LAN (dynamic, may change): `http://<LAN-IP>:8080`

Note: Your LAN IP can change (DHCP). For stable access from other devices, prefer the Tailscale URL above.

## Auth

If `GATEWAY_API_KEYS` is set in `.env`, add `X-API-Key: <your-key>` to every request.
Missing/invalid key returns `401` with JSON: `{"error":"Invalid or missing API key"}`.

## Gateway Routes (Overview)

All routes below are accessed via the gateway base URL.

- LM Studio (OpenAI-compatible): `/lmstudio/v1/...`
- Kokoro TTS: `/kokoro/v1/audio/speech`
- Faster Whisper STT: `/stt/v1/audio/transcriptions`
- OpenRouter (optional): `/openrouter/v1/...`

## LLM (LM Studio, OpenAI-compatible)

- Models: `GET /lmstudio/v1/models`
- Responses: `POST /lmstudio/v1/responses`
- Chat: `POST /lmstudio/v1/chat/completions`
- Completions: `POST /lmstudio/v1/completions`
- Embeddings: `POST /lmstudio/v1/embeddings`

Notes:
- `model` must match an ID from `GET /lmstudio/v1/models`.
- `/v1/responses` is supported on your LM Studio build (validated on the host).
- Typical errors: `401` (missing/invalid API key), `502` (LM Studio not running or unreachable).

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

## TTS (Kokoro)

- Speech: `POST /kokoro/v1/audio/speech`

Notes:
- Returns audio bytes (e.g., MP3). Use `--output` to save.
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
- Returns JSON with a `text` field.

Example:
```bash
curl http://100.120.207.64:8080/stt/v1/audio/transcriptions \
  -H "X-API-Key: <your-key>" \
  -F "file=@sample.wav"
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

## Direct (Non-Gateway) Access (Debug Only)

These are local service ports on the host. Prefer gateway access for clients.

- LM Studio (local app): `http://<HOST-IP>:1234/v1/...`
- Kokoro: `http://<HOST-IP>:8880`
- Faster Whisper REST: `http://<HOST-IP>:10400`
- Faster Whisper (LSIO image): `http://<HOST-IP>:10300`

## LLM Client Quick Start (Prompt Snippet)

Use this snippet to configure LLM agents or external apps:

```
Base URL: http://100.120.207.64:8080
Auth header: X-API-Key: <your-key>
Endpoints:
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

- Kokoro docs: `GET /kokoro/docs`
- STT docs: `GET /stt/docs`
- Gateway errors:
  - `401` = missing/invalid API key
  - `502` = upstream not running/reachable
