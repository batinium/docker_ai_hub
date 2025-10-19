AI Hub Dashboard
================

This directory contains the FastAPI-powered dashboard and helper utilities for the AI Hub environment. It exposes human-friendly cards as well as programmatic entry points that follow the OpenAI REST conventions (chat completions, speech synthesis, audio transcription, etc.).

Quick Start
-----------

1. **Run the services** you want to inspect (LM Studio, Kokoro, Faster Whisper, Open WebUI/Ollama, nginx gateway, …).
2. **Launch the dashboard** (either directly with `uvicorn app:app --reload --port 8090` or via the provided Dockerfile). When running in Docker, create a writable volume for persisted metrics first, e.g. `mkdir -p dashboard/data`.
3. **Visit the UI** at `http://<AIHUB_HOST>:8090` to explore endpoints, sample payloads, and the interactive playground.

Monitoring
----------

The homepage includes a *Gateway Monitoring* card that parses the nginx JSON access log exposed by the proxy and stores each event in SQLite (`MONITORING_DB_PATH`). Mount `./proxy/logs:/var/log/nginx:ro` (already configured in `docker-compose.yml`) so the dashboard can read `/var/log/nginx/access.log`, and mount `./dashboard/data:/app/data` to persist the database across restarts. Adjust the following environment variables to customize behaviour:

- `NGINX_ACCESS_LOG` – Absolute path to the log file if you store it elsewhere.
- `MONITORING_ALERT_WINDOW_MIN` – Rolling window (minutes) used to detect bursts and repeated client errors.
- `MONITORING_RATE_THRESHOLD`, `MONITORING_CLIENT_ERROR_THRESHOLD`, `MONITORING_MISSING_KEY_THRESHOLD` – Tune the heuristics that raise warnings in the UI.
- `MONITORING_DB_PATH`, `MONITORING_STATE_PATH`, `MONITORING_MAX_AGE_DAYS` – Control where events are stored and how long they’re retained.

Paste your dashboard API key into the top bar field to unlock the metrics, live activity table, and alert stream. Data refreshes automatically every minute or whenever you hit the **Refresh** button. If nginx is still emitting the legacy combined format, the ingestion step will parse it (without API-key visibility) and persist the events all the same.

Scripts
-------

- `scripts/connectivity_check.py` &mdash; Automated health probe for each OpenAI-style endpoint. Run `python scripts/connectivity_check.py --mode all` to verify direct container access (`server` mode) and gateway exposure (`client` mode). Environment variables such as `LMSTUDIO_MODEL`, `OLLAMA_MODEL`, `OPENWEBUI_API_KEY`, and port overrides fine-tune the probes.
- `scripts/ai_agent_example.py` &mdash; Annotated reference client you can hand to autonomous agents. It demonstrates how to call LM Studio (direct and via the gateway), Open WebUI/Ollama, Kokoro TTS, and Faster Whisper STT using plain `requests`.

Example commands:

```bash
# Run connectivity checks against the local stack
python scripts/connectivity_check.py --mode server

# Import the example client without executing the demo
python scripts/ai_agent_example.py --no-demo

# Execute the full sample workflow with explicit host/model overrides
python scripts/ai_agent_example.py --host \$LAN_IP --lmstudio-model qwen3-06.b --ollama-model gemma3:4b
```

Security & Sharing
------------------

- Keep secrets (API keys, tokens, gateway credentials) out of source control. The scripts read from the environment so you can export sensitive values at runtime instead of hard-coding them.
- The dashboard and helper scripts are safe to publish **as long as** they do not include real IPs, Tailnet IDs, or credentials. Review diffs carefully before pushing to GitHub.
- If you decide to open-source this folder, document that the services themselves must be protected behind Tailscale/VPN and do not expose them directly to the public internet.
- For AI agents that will run automatically, grant only the minimum privileges required (e.g., create scoped Open WebUI tokens rather than reusing admin accounts).

Extending
---------

Add new services by appending entries to `app.py`'s `SERVICES` list and implementing a corresponding FastAPI route. Follow the existing pattern so the UI automatically renders metadata, payload examples, and playground forms.
