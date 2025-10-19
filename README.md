# AI Hub Workspace

This repository hosts the dashboard, helper scripts, and deployment tooling used to explore and monitor the AI Hub services (LM Studio, Ollama/Open WebUI, Kokoro TTS, Faster-Whisper STT, and the nginx gateway).

## Repository Layout

- `dashboard/` – FastAPI app plus static assets, agent-focused examples, and connectivity tooling.
- `install/` – Convenience scripts that bootstrap Python virtual environments for the server (dashboard host) and client machines.
- `requirements/` – Pinned dependency lists used by the installers.
- `faster-whisper-data/`, `openwebui-data/`, etc. – Service-specific data/cache directories (ignored by Git once populated locally).

## Quick Install

Clone the repository onto the target machine, then pick the path that matches the role you want the machine to play.

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
