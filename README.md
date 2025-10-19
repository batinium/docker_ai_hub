# AI Hub Workspace

This repository hosts the dashboard, helper scripts, and deployment tooling used to explore and monitor the AI Hub services (LM Studio, Ollama/Open WebUI, Kokoro TTS, Faster-Whisper STT, and the nginx gateway).

## Repository Layout

- `dashboard/` – FastAPI app plus static assets, agent-focused examples, and connectivity tooling.
- `install/` – Convenience scripts that bootstrap Python virtual environments for the server (dashboard host) and client machines.
- `requirements/` – Pinned dependency lists used by the installers.
- `faster-whisper-data/`, `openwebui-data/`, etc. – Service-specific data/cache directories (ignored by Git once populated locally).

## Quick Install

Clone the repository onto the target machine, then pick the path that matches the role you want the machine to play.

> Before starting the stack, copy `.env.example` to `.env` and set `LAN_IP` to the host's tunnel/LAN address. All services default to that value (and you can still override `AIHUB_IP` explicitly if needed). If you want the dashboard APIs locked down, populate `DASHBOARD_API_KEYS` (comma-separated) or `DASHBOARD_API_KEY` as well.

### Server (hosts the dashboard)

```bash
git clone <repo-url> && cd aihub
bash install/install_server.sh
source .venv/bin/activate
cd dashboard
uvicorn app:app --host 0.0.0.0 --port 8090
```

The installer creates `.venv/`, installs FastAPI + dependencies from `requirements/server.txt`, and prints next steps for starting the dashboard. Ensure the machine can reach LM Studio, Kokoro, Faster-Whisper, and the gateway over Tailscale or your internal network.

### Client (connectivity checks or agent playground)

```bash
git clone <repo-url> && cd aihub
bash install/install_client.sh
source .venv-client/bin/activate
cd dashboard
python scripts/connectivity_check.py --mode client
```

This lightweight environment only installs `requests` and is enough to run the connectivity script or the agent example without pulling in the entire FastAPI stack.

## Sharing & Security

- It is safe to publish the code as long as you remove secrets (API keys, Tailnet IPs, generated logs). The `.gitignore` file keeps common artifacts out of version control.
- Treat the repository as **documentation plus tooling**. The services themselves must remain behind your VPN/Tailscale network; do not expose their ports directly to the public internet.
- If you plan to open-source the project, scrub commit history for credentials, rotate any keys you’ve shared previously, and consider keeping deployment specifics (compose files, scripts with hostnames) in a private companion repo.

## Extending

To add a new service card and proxy:

1. Update `dashboard/app.py` by appending a new entry to `SERVICES` and implementing the associated FastAPI route.
2. Static assets auto-refresh thanks to the declarative metadata—no template edits are required.
3. Document the change in `dashboard/AGENTS.md` so teammates and agents understand the new capability.

## Container Management

Start, stop, or refresh the stack from the repository root with Docker Compose. The compose file names the core containers `aihub_dashboard`, `faster_whisper_rest`, `ai_proxy_gateway`, `openwebui`, `faster-whisper`, and `kokoro`.

- **Start / restart everything**
  ```bash
  docker compose up -d
  docker ps --format 'table {{.Names}}\t{{.Status}}'
  ```
  The `docker ps` check helps confirm each container came up as expected.

- **Stop or tear down**
  ```bash
  docker compose stop          # keep volumes/images
  docker compose down          # stop and drop the network
  ```

- **Update images and rebuild local services**
  ```bash
  docker compose pull                     # refresh remote images (nginx, Open WebUI, Kokoro, etc.)
  docker compose build aihub_dashboard    # rebuild the dashboard image after code changes
  docker compose build faster_whisper_rest
  docker compose up -d                    # restart everything with the new builds
  ```
  To reload a single service after rebuilding it, target the container: `docker compose up -d aihub_dashboard`.

- **Gateway routing**
  - The `ai_proxy_gateway` container now fronts LM Studio (`/lmstudio/`), Ollama (`/ollama/`), Kokoro (`/kokoro/`), Open WebUI (`/openwebui/`), and Faster Whisper REST (`/stt/`). Point clients at `http://<tailnet-ip>:8080/<service>/…` instead of hitting individual ports.
  - Keep the upstream containers private; only expose the gateway port over Tailscale or your VPN.

- **Quick rebuild helper**
  ```bash
  ./scripts/rebuild_services.sh          # interactive picker
  ./scripts/rebuild_services.sh proxy-gateway aihub_dashboard
  ```
  The script wraps `docker compose build` + `docker compose up -d` so you can pick the services to rebuild and restart without typing long commands.

- **Gateway smoke-tests**
  ```bash
  python dashboard/scripts/connectivity_check.py --mode all --ip <tailnet-ip>
  ```
  Every probe goes through the gateway (`/lmstudio/`, `/ollama/`, `/kokoro/`, `/openwebui/`, `/stt/`). The table reports success, HTTP status, latency, and a short detail line so you can quickly spot issues after a redeploy.

- **Configure Open WebUI (custom OpenAI providers)**
  - **Text-to-Speech (Kokoro)**: set engine to `OpenAI`, base URL to `http://$LAN_IP:8080/kokoro/v1`, model `kokoro`, voice `af_bella`, leave the API key blank or `not-needed`, and keep response splitting at `punctuation` unless you want paragraph-level chunking.
  - **Speech-to-Text (Faster Whisper)**: set engine to `OpenAI`, base URL to `http://$LAN_IP:8080/stt/v1`, model `small.en` (or the one you deploy), leave the API key blank; if the UI insists on a key you can use `not-needed`.
  - When Open WebUI runs inside Docker on the same host, you can substitute `$LAN_IP` with `host.docker.internal` to avoid leaking the tailnet/Gateway IP.

- **Dashboard API keys**
  - Populate `DASHBOARD_API_KEYS` (comma-separated) or `DASHBOARD_API_KEY` in `.env` to require an `X-API-Key` header on every `/api/...` call. Leave both empty to keep the dashboard open on trusted networks.
  - After the dashboard reloads, paste one of the keys into the "Dashboard API Key" form at the top of the page; the key stays in your browser’s local storage and is not rendered server-side.
  - CLI helpers (`dashboard/scripts/ai_agent_example.py`, `dashboard/scripts/connectivity_check.py`) pick up `DASHBOARD_API_KEY`/`DASHBOARD_API_KEYS` automatically. Override with `--dashboard-api-key` when running manually.

- **Inspect logs on a misbehaving container**
  ```bash
  docker compose logs -f openwebui
  ```

## Client & Agent References

- `dashboard/scripts/ai_agent_example.py` demos gateway calls for LM Studio, Ollama, Kokoro, Faster Whisper, and Open WebUI. Run it with `--no-demo` to sanity-check imports, or adjust the CLI flags/environment variables (including `--dashboard-api-key`) to exercise specific models.
- `dashboard/scripts/connectivity_check.py` runs quick health probes against every gateway path. Pass `--dashboard-api-key` (or export `DASHBOARD_API_KEY`) if the dashboard requires authentication.
- `dashboard/AGENTS.md` lists every dashboard card, the gateway path it targets, and tips for adding new services. Keep the table up to date when you introduce additional routes.
