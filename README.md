# AI Hub Gateway

Minimal gateway for local AI services. This stack exposes LM Studio, Kokoro TTS, and Faster Whisper via a single nginx proxy, optionally relaying OpenRouter.

## Highlights

- **Single Gateway** – nginx fronts all services on one port.
- **Tailscale-Friendly** – advertise your tailnet IP to remote agents.
- **Optional Auth** – simple `X-API-Key` gate when `GATEWAY_API_KEY` is set.
- **No UI** – no dashboard or custom frontend to maintain.

## Services

| Service | Gateway Path | Notes |
| --- | --- | --- |
| LM Studio | `/lmstudio/v1/...` | OpenAI-compatible models, responses, chat, completions, embeddings |
| Kokoro TTS | `/kokoro/v1/audio/speech` | MP3 output |
| Faster Whisper STT | `/stt/v1/audio/transcriptions` | Multipart audio upload |
| OpenRouter (optional) | `/openrouter/v1/...` | Requires `OPENROUTER_API_KEY` |

## Quick Start

1) **Create `.env`:**
```bash
cp .env.example .env
```
Set:
- `LAN_IP` / `AIHUB_IP` to your tailnet IP (example: `100.120.207.64`)
- `LMSTUDIO_HOST` to the Windows host IP (example: `192.168.1.103`)
- `GATEWAY_API_KEYS` if you want requests locked down (comma-separated)

2) **Create data dirs:**
```bash
mkdir -p proxy/logs faster-whisper-data
```

3) **Start services:**
```bash
docker compose up -d --build
```

## Connectivity Check

```bash
python scripts/connectivity_check.py --mode client --ip 100.120.207.64 --gateway-port 8080 --lmstudio-model "google/gemma-3-4b"
```

## Gateway Auth

If `GATEWAY_API_KEYS` is set, send `X-API-Key` on every request. Example:
```bash
curl http://100.120.207.64:8080/lmstudio/v1/models \
  -H "X-API-Key: your-key"
```

## OpenRouter

Set `OPENROUTER_API_KEY` in `.env`, then call:
```bash
curl http://100.120.207.64:8080/openrouter/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"openrouter/auto","messages":[{"role":"user","content":"Hello"}]}'
```
The gateway injects the real key server-side.

## Layout

- `proxy/` – nginx gateway template
- `faster_whisper_rest/` – REST wrapper for Faster Whisper
- `scripts/` – connectivity check utilities
- `AGENTS.md` – agent-facing endpoint guide
