# AI Hub Gateway

Minimal gateway for local AI services. This stack exposes LM Studio, llama.cpp, Kokoro TTS, and Faster Whisper via a single nginx proxy, optionally relaying OpenRouter.

## Highlights

- **Single Gateway** – nginx fronts all services on one port.
- **Tailscale-Friendly** – advertise your tailnet IP to remote agents.
- **GPU Accelerated** – uses NVIDIA GPU reservations for blazingly fast Kokoro TTS and Faster Whisper STT responses.
- **TTS Caching** – exact POST match JSON bodies skip generation and return cached MP3 instantly.
- **Rate-Limited Resiliency** – proxy connections limit excessive endpoint abuse to protect host hardware.
- **Optional Auth** – simple `X-API-Key` gate when `GATEWAY_API_KEYS` is set.
- **No UI** – no dashboard or custom frontend to maintain.

## Services

| Service | Gateway Path | Notes |
| --- | --- | --- |
| LM Studio | `/lmstudio/v1/...` | OpenAI-compatible models, responses, chat, completions, embeddings |
| llama.cpp | `/llama/v1/...` | GPU-backed GGUF models through llama.cpp server, OpenAI-compatible chat/completions/embeddings |
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
- `LMSTUDIO_HOST` to the machine/address that actually runs LM Studio from Docker's point of view
- `LMSTUDIO_HOST` should usually be `host.docker.internal` on Docker Desktop, or your host LAN IP on Linux (example: `192.168.1.103`)
- `LLAMA_CPP_MODELS_DIR` to the host model root (for example `/mnt/d/LMStudio/models` when using LM Studio's Windows model cache from WSL)
- `LLAMA_CPP_MODEL` to the GGUF path inside the container (for example `/models/qwen2.5-7b-instruct-q4_k_m.gguf`)
- `LLAMA_CPP_MODEL_ALIAS` to the model ID clients should send (default: `local-gguf`; this deployment uses `qwen2.5-7b-instruct`)
- `GATEWAY_API_KEYS` if you want requests locked down (comma-separated)

Do not point `LMSTUDIO_HOST` at the public gateway IP (`LAN_IP` / `AIHUB_IP` / Tailscale IP). That makes nginx proxy `/lmstudio/*` back to the gateway address instead of to LM Studio itself, which typically fails with `502 Bad Gateway` or upstream connection errors.

2) **Create data dirs and add a GGUF model:**
```bash
mkdir -p proxy/logs faster-whisper-data llama-models
```
Place your `.gguf` model under `llama-models/`, then set `LLAMA_CPP_MODEL=/models/<file>.gguf` in `.env`.
For the LM Studio cache, set `LLAMA_CPP_MODELS_DIR=/mnt/d/LMStudio/models` and use the path below that root, for example `LLAMA_CPP_MODEL=/models/lmstudio-community/Qwen2.5-7B-Instruct-GGUF/Qwen2.5-7B-Instruct-Q4_K_M.gguf`.

3) **Start services:**
```bash
docker compose up -d --build
```

## llama.cpp

The llama.cpp container uses the official CUDA server image and reserves one NVIDIA GPU. `LLAMA_CPP_N_GPU_LAYERS=999` asks llama.cpp to offload all possible layers to the RTX 5090; reduce it only when you need to fit a larger model or compare CPU/GPU behavior.

The current gateway deployment mounts the LM Studio model cache and serves `/models/lmstudio-community/Qwen2.5-7B-Instruct-GGUF/Qwen2.5-7B-Instruct-Q4_K_M.gguf` as `qwen2.5-7b-instruct`.

```bash
curl http://100.120.207.64:8080/llama/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"model":"qwen2.5-7b-instruct","messages":[{"role":"user","content":"Hello"}]}'
```

## Connectivity Check

```bash
python scripts/connectivity_check.py --mode client --ip 100.120.207.64 --gateway-port 8080 --llama-model qwen2.5-7b-instruct --lmstudio-model "" --openrouter-model ""
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
