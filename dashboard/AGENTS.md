# AI Hub Agents Handbook

This repository hosts the FastAPI dashboard that exposes the core AI Hub services running on the local Mac, making them discoverable and testable for remote teammates that connect over Tailscale. Use this doc as the authoritative reference when extending or operating the hub.

## Platform Overview

- **Networking:** All access happens over the Tailscale mesh; share the Mac’s Tailscale tailnet IP (`{{TAILSCALE_IP}}` placeholder) with trusted clients.
- **Dashboard:** `uvicorn app:app` (containerised via the provided `Dockerfile`) serves the interactive guide on port `8090`. It proxies requests to the underlying containers so users can exercise APIs without leaving the UI.
- **Static outputs:** Generated assets (e.g. MP3 from Kokoro) are stored under `static/tts_outputs/` and are exposed at `/static/tts_outputs/<filename>` for download.

### Current Service Catalogue

The catalogue is defined in `app.py` as the `SERVICES` list; the UI renders it automatically and exposes it via `/api/services`. Each entry requires:

| ID | Provider | Local Endpoint | Upstream Target | Brief |
| --- | --- | --- | --- | --- |
| `lmstudio-chat` | LM Studio | `POST /api/chat` | `http://AIHUB_IP:1234/v1/chat/completions` | OpenAI-compatible chat completions. |
| `lmstudio-models` | LM Studio | `POST /api/lmstudio/models` | `http://AIHUB_IP:1234/v1/models` | Fetch the upstream model catalogue. |
| `kokoro-tts` | Kokoro | `POST /api/tts` | `http://AIHUB_IP:8880/v1/audio/speech` | Text-to-Speech returning downloadable MP3. |
| `faster-whisper-stt` | Faster Whisper REST | `POST /api/stt` | `http://AIHUB_IP:10400/v1/audio/transcriptions` | Speech-to-text via multipart upload. |
| `openwebui-chat` | Open WebUI | `POST /api/openwebui/chat` | `http://AIHUB_IP:3000/api/chat/completions` | Chat completions routed to Open WebUI. |
| `gateway-lmstudio-chat` | Nginx Gateway | `POST /api/gateway/chat` | `http://AIHUB_IP:8080/lmstudio/v1/chat/completions` | Same LM Studio chat via the shared gateway. |

Add new services by appending to the list; include metadata, form defaults, and `curl_example`. No template updates are required.

## Operating Procedures

1. **Build & run (Docker):**
   ```bash
   docker build -t aihub-dashboard .
   docker run --rm -p 8090:8090 aihub-dashboard
   ```
   Ensure the container can reach peers (LM Studio, Kokoro, Faster Whisper) on the Tailscale network; run `tailscale status` on the host if connectivity fails.

2. **Connectivity check:** Use `scripts/connectivity_check.py` to exercise every OpenAI-style endpoint.
   ```bash
   python scripts/connectivity_check.py --mode server
   python scripts/connectivity_check.py --mode client
   ```
   The `server` mode hits container ports directly; `client` mode uses the nginx gateway. Defaults target `LM Studio → qwen3-0.6b` and `Ollama/Open WebUI → gemma3:4b`, but you can override with `--lmstudio-model`, `--ollama-model` (also drives Open WebUI), or the associated environment variables (`LMSTUDIO_MODEL`, `OLLAMA_MODEL`, etc.). If Open WebUI requires an API key, export `OPENWEBUI_API_KEY`; otherwise a 401 is treated as “reachable but auth required.” A non-zero exit signals at least one failing check.

3. **File persistence:** `static/tts_outputs/` is bind-mounted automatically when running locally. If you run in a container without volume mounts, you must copy the outputs out of the container or provide an external volume.

4. **Security:** Expose the dashboard only to authenticated Tailscale peers; do not bind the container to a public interface without additional auth.

## Development Notes

- **Templates & styling:** Located in `templates/index.html` and `static/css/style.css`. JavaScript lives at `static/js/main.js` and handles playground submissions, clipboard copy, and response rendering.
- **Config via env:** Override `AIHUB_IP`, `LMSTUDIO_PORT`, `KOKORO_PORT`, `STT_REST_PORT`, `OPENWEBUI_PORT`, or `GATEWAY_PORT` as needed. Set `OPENWEBUI_API_KEY` if the upstream requires authentication.
- **Extensibility:** Keep services declarative. For new agents (e.g., image generation, vector DB), provide:
  - `id`, `name`, `provider`, `category`
  - `local_endpoint` (FastAPI route you implement)
  - `upstream_endpoint` (where requests are proxied)
  - `sample_payload`, `curl_example`, `form_defaults`
  - Optional `notes`, `inputs` array for UI hints

## Troubleshooting Checklist

- Dashboard loads but calls fail → verify Tailscale route, container firewall, and upstream services’ health.
- MP3 doesn’t download → confirm `/static` mount is reachable and Kokoro response is non-empty; check FastAPI logs for write errors.
- UI stalls on submit → inspect browser console; ensure CORS is not blocking (local proxy uses same origin).

Keep this guide updated as new agents join the hub so all collaborators share the same map of the system.
