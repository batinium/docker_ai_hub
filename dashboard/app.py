# ~/aihub/dashboard/app.py

import json
import os
import re
import sqlite3
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Callable

import requests
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

# -- CONFIGURATION
BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

DEFAULT_IP = os.environ.get("LAN_IP", "127.0.0.1")
AIHUB_IP = os.environ.get("AIHUB_IP", DEFAULT_IP)
LMSTUDIO_PORT = int(os.environ.get("LMSTUDIO_PORT", 1234))
KOKORO_PORT   = int(os.environ.get("KOKORO_PORT", 8880))
STT_REST_PORT = int(os.environ.get("STT_REST_PORT", 10400))
OPENWEBUI_PORT = int(os.environ.get("OPENWEBUI_PORT", 3000))
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", 8080))
LMSTUDIO_DEFAULT_MODEL = os.environ.get("LMSTUDIO_MODEL", "qwen3-06.b")
STATIC_VERSION = os.environ.get("STATIC_VERSION") or str(int(time.time()))
GATEWAY_BASE = f"http://{AIHUB_IP}:{GATEWAY_PORT}"
OPENWEBUI_API_KEY = os.environ.get("OPENWEBUI_API_KEY")
DASHBOARD_API_KEYS = [
    key.strip()
    for key in os.environ.get("DASHBOARD_API_KEYS", "").split(",")
    if key.strip()
]
PRIMARY_DASHBOARD_API_KEY = DASHBOARD_API_KEYS[0] if DASHBOARD_API_KEYS else None


def gateway_headers(extra: dict | None = None) -> dict:
    headers: dict[str, str] = {}
    if extra:
        headers.update(extra)
    if PRIMARY_DASHBOARD_API_KEY:
        headers.setdefault("X-API-Key", PRIMARY_DASHBOARD_API_KEY)
    return headers


def _parse_ignore_list(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    tokens = re.split(r"[,\s]+", raw)
    ordered: list[str] = []
    for token in tokens:
        candidate = token.strip()
        if not candidate or candidate in ordered:
            continue
        ordered.append(candidate)
    return tuple(ordered)


MONITORING_IGNORE_CLIENTS = _parse_ignore_list(os.environ.get("MONITORING_IGNORE_CLIENTS"))
MONITORING_FILTERS_ACTIVE = bool(MONITORING_IGNORE_CLIENTS)

PORTS = {
    "lmstudio": LMSTUDIO_PORT,
    "kokoro": KOKORO_PORT,
    "stt": STT_REST_PORT,
    "openwebui": OPENWEBUI_PORT,
    "gateway": GATEWAY_PORT,
}

NGINX_ACCESS_LOG = Path(os.environ.get("NGINX_ACCESS_LOG", "/var/log/nginx/access.log"))
MONITORING_MAX_SCAN = int(os.environ.get("MONITORING_MAX_SCAN", "10000"))
MONITORING_DEFAULT_LIMIT = int(os.environ.get("MONITORING_DEFAULT_LIMIT", "200"))
MONITORING_ALERT_WINDOW_MIN = int(os.environ.get("MONITORING_ALERT_WINDOW_MIN", "60"))
ALERT_CLIENT_ERROR_THRESHOLD = int(os.environ.get("MONITORING_CLIENT_ERROR_THRESHOLD", "12"))
ALERT_RATE_THRESHOLD = int(os.environ.get("MONITORING_RATE_THRESHOLD", "120"))
ALERT_MISSING_KEY_THRESHOLD = int(os.environ.get("MONITORING_MISSING_KEY_THRESHOLD", "25"))
SUSPICIOUS_PATH_HINTS = [
    "../",
    "/etc/passwd",
    "/wp-admin",
    "/.git",
    "/phpmyadmin",
]
MONITORING_DB_PATH = Path(
    os.environ.get("MONITORING_DB_PATH") or (BASE_DIR / "data" / "monitoring.sqlite3")
)
MONITORING_STATE_PATH = Path(
    os.environ.get("MONITORING_STATE_PATH") or (BASE_DIR / "data" / "monitoring_state.json")
)
MONITORING_MAX_AGE_DAYS = int(os.environ.get("MONITORING_MAX_AGE_DAYS", "30"))
INGEST_LOCK = threading.Lock()
COMBINED_LOG_RE = re.compile(
    (
        r'(?P<remote_addr>\S+) \S+ \S+ '
        r'\[(?P<time>[^\]]+)\] '
        r'"(?P<request>[^"]*)" '
        r'(?P<status>\d{3}) (?P<body_bytes_sent>\S+) '
        r'"(?P<http_referer>[^"]*)" '
        r'"(?P<user_agent>[^"]*)"'
    )
)

SERVICES = [
    {
        "id": "lmstudio-chat",
        "name": "Chat Completions",
        "provider": "LM Studio",
        "category": "Language Models",
        "method": "POST",
        "local_endpoint": "/api/chat",
        "upstream_endpoint": f"{GATEWAY_BASE}/lmstudio/v1/chat/completions",
        "summary": "Send chat style prompts to LM Studio compatible models via the nginx gateway.",
        "inputs": [
            {"field": "model", "type": "text", "description": "Model identifier hosted on LM Studio."},
            {"field": "message", "type": "textarea", "description": "User message; server prepends system prompt if configured downstream."}
        ],
        "notes": [
            "LM Studio follows the OpenAI Chat Completions schema.",
            "Set `stream` to true if you want server side streaming and can handle SSE."
        ],
        "sample_payload": {
            "model": LMSTUDIO_DEFAULT_MODEL,
            "messages": [{"role": "user", "content": "Hello, AI Hub!"}],
            "stream": False
        },
        "form_defaults": {
            "model": LMSTUDIO_DEFAULT_MODEL,
            "message": "What tools are available on AI Hub right now?"
        },
        "curl_example": "\n".join([
            "curl -X POST \\",
            f"  {GATEWAY_BASE}/lmstudio/v1/chat/completions \\",
            "  -H 'Content-Type: application/json' \\",
            "  -H 'X-API-Key: YOUR_DASHBOARD_API_KEY' \\",
            "  -d '{\"model\":\"" + LMSTUDIO_DEFAULT_MODEL + "\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello, AI Hub!\"}],\"stream\":false}'"
        ]),
        "python_example": "\n".join([
            "import requests",
            "",
            f"url = \"{GATEWAY_BASE}/lmstudio/v1/chat/completions\"",
            "payload = {",
                "    \"model\": \"" + LMSTUDIO_DEFAULT_MODEL + "\",",
                "    \"messages\": [{\"role\": \"user\", \"content\": \"Hello, AI Hub!\"}],",
                "    \"stream\": False",
            "}",
            "headers = {\"X-API-Key\": \"YOUR_DASHBOARD_API_KEY\"}",
            "response = requests.post(url, json=payload, headers=headers, timeout=60)",
            "response.raise_for_status()",
            "print(response.json())",
        ]),
    },
    {
        "id": "lmstudio-models",
        "name": "List Models",
        "provider": "LM Studio",
        "category": "Language Models",
        "method": "POST",
        "local_endpoint": "/api/lmstudio/models",
        "upstream_endpoint": f"{GATEWAY_BASE}/lmstudio/v1/models",
        "summary": "Enumerate all models exposed by LM Studio.",
        "inputs": [],
        "notes": [
            "Upstream request is a GET; the dashboard proxies via POST for convenience.",
            "Use returned IDs when calling chat or completion endpoints."
        ],
        "sample_payload": {
            "method": "GET",
            "url": f"{GATEWAY_BASE}/lmstudio/v1/models"
        },
        "form_defaults": {},
        "curl_example": "\n".join([
            "curl -X GET \\",
            f"  {GATEWAY_BASE}/lmstudio/v1/models \\",
            "  -H 'X-API-Key: YOUR_DASHBOARD_API_KEY'"
        ]),
        "python_example": "\n".join([
            "import requests",
            "",
            f"url = \"{GATEWAY_BASE}/lmstudio/v1/models\"",
            "headers = {\"X-API-Key\": \"YOUR_DASHBOARD_API_KEY\"}",
            "response = requests.get(url, headers=headers, timeout=30)",
            "response.raise_for_status()",
            "data = response.json()",
            "for model in data.get(\"data\", data.get(\"models\", [])):",
            "    print(model.get(\"id\", \"(unknown id)\"))",
        ]),
    },
    {
        "id": "lmstudio-responses",
        "name": "Responses API",
        "provider": "LM Studio",
        "category": "Language Models",
        "method": "POST",
        "local_endpoint": "/api/lmstudio/responses",
        "upstream_endpoint": f"{GATEWAY_BASE}/lmstudio/v1/responses",
        "summary": "Call the OpenAI-compatible Responses endpoint exposed by LM Studio through the gateway.",
        "inputs": [
            {"field": "model", "type": "text", "description": "Model identifier that can handle the Responses API."},
            {"field": "prompt", "type": "textarea", "description": "Prompt text sent as the `input` payload."}
        ],
        "notes": [
            "Responses API is ideal for free-form prompts that do not follow chat semantics.",
            "Add `stream` or additional parameters by extending the server-side proxy logic."
        ],
        "sample_payload": {
            "model": LMSTUDIO_DEFAULT_MODEL,
            "input": "Briefly describe the AI Hub architecture."
        },
        "form_defaults": {
            "model": LMSTUDIO_DEFAULT_MODEL,
            "prompt": "Briefly describe the AI Hub architecture."
        },
        "curl_example": "\n".join([
            "curl -X POST \\",
            f"  {GATEWAY_BASE}/lmstudio/v1/responses \\",
            "  -H 'Content-Type: application/json' \\",
            "  -H 'X-API-Key: YOUR_DASHBOARD_API_KEY' \\",
            "  -d '{\"model\":\"" + LMSTUDIO_DEFAULT_MODEL + "\",\"input\":\"Briefly describe the AI Hub architecture.\"}'"
        ]),
        "python_example": "\n".join([
            "import requests",
            "",
            f"url = \"{GATEWAY_BASE}/lmstudio/v1/responses\"",
            "payload = {",
                "    \"model\": \"" + LMSTUDIO_DEFAULT_MODEL + "\",",
                "    \"input\": \"Briefly describe the AI Hub architecture.\"",
            "}",
            "headers = {\"X-API-Key\": \"YOUR_DASHBOARD_API_KEY\"}",
            "response = requests.post(url, json=payload, headers=headers, timeout=60)",
            "response.raise_for_status()",
            "print(response.json())",
        ]),
    },
    {
        "id": "lmstudio-completions",
        "name": "Completions API",
        "provider": "LM Studio",
        "category": "Language Models",
        "method": "POST",
        "local_endpoint": "/api/lmstudio/completions",
        "upstream_endpoint": f"{GATEWAY_BASE}/lmstudio/v1/completions",
        "summary": "Legacy text completions endpoint compatible with OpenAI-style models via the gateway.",
        "inputs": [
            {"field": "model", "type": "text", "description": "Model identifier for completion style prompts."},
            {"field": "prompt", "type": "textarea", "description": "Text prompt to complete."},
            {"field": "max_tokens", "type": "text", "description": "Optional max token budget for the response."}
        ],
        "notes": [
            "Leave max tokens blank to use the upstream default.",
            "Switch to the Responses API for richer multi-turn or tool calling interactions."
        ],
        "sample_payload": {
            "model": LMSTUDIO_DEFAULT_MODEL,
            "prompt": "Write a short promotional slogan for AI Hub:",
            "max_tokens": 120
        },
        "form_defaults": {
            "model": LMSTUDIO_DEFAULT_MODEL,
            "prompt": "Write a short promotional slogan for AI Hub:",
            "max_tokens": "120"
        },
        "curl_example": "\n".join([
            "curl -X POST \\",
            f"  {GATEWAY_BASE}/lmstudio/v1/completions \\",
            "  -H 'Content-Type: application/json' \\",
            "  -H 'X-API-Key: YOUR_DASHBOARD_API_KEY' \\",
            "  -d '{\"model\":\"" + LMSTUDIO_DEFAULT_MODEL + "\",\"prompt\":\"Write a short promotional slogan for AI Hub:\",\"max_tokens\":120}'"
        ]),
        "python_example": "\n".join([
            "import requests",
            "",
            f"url = \"{GATEWAY_BASE}/lmstudio/v1/completions\"",
            "payload = {",
                "    \"model\": \"" + LMSTUDIO_DEFAULT_MODEL + "\",",
                "    \"prompt\": \"Write a short promotional slogan for AI Hub:\",",
                "    \"max_tokens\": 120",
            "}",
            "headers = {\"X-API-Key\": \"YOUR_DASHBOARD_API_KEY\"}",
            "response = requests.post(url, json=payload, headers=headers, timeout=60)",
            "response.raise_for_status()",
            "print(response.json())",
        ]),
    },
    {
        "id": "lmstudio-embeddings",
        "name": "Embeddings API",
        "provider": "LM Studio",
        "category": "Language Models",
        "method": "POST",
        "local_endpoint": "/api/lmstudio/embeddings",
        "upstream_endpoint": f"{GATEWAY_BASE}/lmstudio/v1/embeddings",
        "summary": "Generate embeddings vectors for search or retrieval augmented pipelines via the gateway.",
        "inputs": [
            {"field": "model", "type": "text", "description": "Embedding-capable model identifier."},
            {"field": "text", "type": "textarea", "description": "Content to embed; supports batching when extended."}
        ],
        "notes": [
            "Ensure the selected model can produce embeddings; see LM Studio docs for compatible options.",
            "Returned vectors are large; the playground shows a preview of the upstream JSON payload."
        ],
        "sample_payload": {
            "model": "text-embedding-qwen3-embedding-0.6b",
            "input": "Embedding probe for AI Hub services."
        },
        "form_defaults": {
            "model": "text-embedding-qwen3-embedding-0.6b",
            "text": "Embedding probe for AI Hub services."
        },
        "curl_example": "\n".join([
            "curl -X POST \\",
            f"  {GATEWAY_BASE}/lmstudio/v1/embeddings \\",
            "  -H 'Content-Type: application/json' \\",
            "  -H 'X-API-Key: YOUR_DASHBOARD_API_KEY' \\",
            "  -d '{\"model\":\"text-embedding-qwen3-embedding-0.6b\",\"input\":\"Embedding probe for AI Hub services.\"}'"
        ]),
        "python_example": "\n".join([
            "import requests",
            "",
            f"url = \"{GATEWAY_BASE}/lmstudio/v1/embeddings\"",
            "payload = {",
                "    \"model\": \"text-embedding-qwen3-embedding-0.6b\",",
                "    \"input\": \"Embedding probe for AI Hub services.\"",
            "}",
            "headers = {\"X-API-Key\": \"YOUR_DASHBOARD_API_KEY\"}",
            "response = requests.post(url, json=payload, headers=headers, timeout=60)",
            "response.raise_for_status()",
            "embedding = response.json().get(\"data\", [{}])[0].get(\"embedding\", [])",
            "print(f\"Dimensions: {len(embedding)}\")",
        ]),
    },
    {
        "id": "kokoro-tts",
        "name": "Text to Speech",
        "provider": "Kokoro",
        "category": "Audio",
        "method": "POST",
        "local_endpoint": "/api/tts",
        "upstream_endpoint": f"{GATEWAY_BASE}/kokoro/v1/audio/speech",
        "summary": "Turn text prompts into MP3 audio using Kokoro voices via the gateway.",
        "inputs": [
            {"field": "text", "type": "textarea", "description": "Sentence or paragraph to synthesize."},
            {"field": "voice", "type": "text", "description": "Voice preset such as `af_bella` or `am_matthew`."}
        ],
        "notes": [
            "Audio is cached under `/static/tts_outputs` for quick re-download.",
            "Set `speed` in the payload if you need faster or slower speech."
        ],
        "sample_payload": {
            "model": "kokoro",
            "input": "Hello from AI Hub!",
            "voice": "af_bella",
            "response_format": "mp3",
            "speed": 1.0
        },
        "form_defaults": {
            "text": "Hello from AI Hub, bridging models and utilities.",
            "voice": "af_bella"
        },
        "curl_example": "\n".join([
            "curl -X POST \\",
            f"  {GATEWAY_BASE}/kokoro/v1/audio/speech \\",
            "  -H 'Content-Type: application/json' \\",
            "  -H 'X-API-Key: YOUR_DASHBOARD_API_KEY' \\",
            "  -d '{\"model\":\"kokoro\",\"input\":\"Hello from AI Hub!\",\"voice\":\"af_bella\",\"response_format\":\"mp3\",\"speed\":1.0}' \\",
            "  --output output.mp3"
        ]),
        "python_example": "\n".join([
            "import requests",
            "",
            f"url = \"{GATEWAY_BASE}/kokoro/v1/audio/speech\"",
            "payload = {",
                "    \"model\": \"kokoro\",",
                "    \"input\": \"Hello from AI Hub!\",",
                "    \"voice\": \"af_bella\",",
                "    \"response_format\": \"mp3\",",
                "    \"speed\": 1.0",
            "}",
            "headers = {\"X-API-Key\": \"YOUR_DASHBOARD_API_KEY\"}",
            "response = requests.post(url, json=payload, headers=headers, timeout=60)",
            "response.raise_for_status()",
            "with open(\"output.mp3\", \"wb\") as fh:",
            "    fh.write(response.content)",
            "print(\"Saved audio to output.mp3\")",
        ]),
    },
    {
        "id": "openwebui-chat",
        "name": "Chat (Open WebUI)",
        "provider": "Open WebUI",
        "category": "Language Models",
        "method": "POST",
        "local_endpoint": "/api/openwebui/chat",
        "upstream_endpoint": f"{GATEWAY_BASE}/openwebui/api/chat/completions",
        "summary": "Send chat prompts to models orchestrated by Open WebUI using the OpenAI schema via the gateway.",
        "inputs": [
            {"field": "model", "type": "text", "description": "Model identifier registered inside Open WebUI."},
            {"field": "message", "type": "textarea", "description": "Prompt content forwarded by Open WebUI."}
        ],
        "notes": [
            "Set the `OPENWEBUI_API_KEY` environment variable if the upstream instance enforces authentication.",
            "Open WebUI exposes additional APIs (images, tools); extend the dashboard with new entries as needed."
        ],
        "sample_payload": {
            "model": "qwen2.5:7b-instruct",
            "messages": [{"role": "user", "content": "Summarize the AI Hub services."}]
        },
        "form_defaults": {
            "model": "qwen2.5:7b-instruct",
            "message": "Summarize the AI Hub services available over Tailscale."
        },
        "curl_example": "\n".join([
            "curl -X POST \\",
            f"  {GATEWAY_BASE}/openwebui/api/chat/completions \\",
            "  -H 'Content-Type: application/json' \\",
            "  -H 'X-API-Key: YOUR_DASHBOARD_API_KEY' \\",
            "  -d '{\"model\":\"qwen2.5:7b-instruct\",\"messages\":[{\"role\":\"user\",\"content\":\"Summarize the AI Hub services.\"}]}'"
        ]),
        "python_example": "\n".join([
            "import requests",
            "",
            f"url = \"{GATEWAY_BASE}/openwebui/api/chat/completions\"",
            "payload = {",
                "    \"model\": \"qwen2.5:7b-instruct\",",
                "    \"messages\": [{\"role\": \"user\", \"content\": \"Summarize the AI Hub services.\"}],",
            "}",
            "headers = {",
            "    \"X-API-Key\": \"YOUR_DASHBOARD_API_KEY\",",
            "    \"Authorization\": \"Bearer YOUR_OPENWEBUI_KEY\",",
            "}",
            "response = requests.post(url, json=payload, headers=headers, timeout=60)",
            "response.raise_for_status()",
            "print(response.json())",
        ]),
    },
    {
        "id": "gateway-ollama-chat",
        "name": "Gateway Ollama Chat",
        "provider": "Ollama",
        "category": "Gateway",
        "method": "POST",
        "local_endpoint": "/api/gateway/ollama/chat",
        "upstream_endpoint": f"{GATEWAY_BASE}/ollama/v1/chat/completions",
        "summary": "Exercise the nginx relay that fronts the Ollama API.",
        "inputs": [
            {"field": "model", "type": "text", "description": "Ollama model identifier (e.g. `gemma3:4b`)."},
            {"field": "message", "type": "textarea", "description": "Prompt forwarded through the gateway to Ollama."}
        ],
        "notes": [
            "Gateway mirrors the native Ollama chat completions endpoint.",
            "Ensure the Ollama service is listening on the host; enable the compose service if it is not running."
        ],
        "sample_payload": {
            "model": "gemma3:4b",
            "messages": [{"role": "user", "content": "Verify Ollama gateway routing."}],
            "stream": False
        },
        "form_defaults": {
            "model": "gemma3:4b",
            "message": "Verify Ollama gateway routing."
        },
        "curl_example": "\n".join([
            "curl -X POST \\",
            f"  {GATEWAY_BASE}/ollama/v1/chat/completions \\",
            "  -H 'Content-Type: application/json' \\",
            "  -H 'X-API-Key: YOUR_DASHBOARD_API_KEY' \\",
            "  -d '{\"model\":\"gemma3:4b\",\"messages\":[{\"role\":\"user\",\"content\":\"Verify Ollama gateway routing.\"}],\"stream\":false}'"
        ]),
        "python_example": "\n".join([
            "import requests",
            "",
            f"url = \"{GATEWAY_BASE}/ollama/v1/chat/completions\"",
            "payload = {",
                "    \"model\": \"gemma3:4b\",",
                "    \"messages\": [{\"role\": \"user\", \"content\": \"Verify Ollama gateway routing.\"}],",
                "    \"stream\": False",
            "}",
            "headers = {\"X-API-Key\": \"YOUR_DASHBOARD_API_KEY\"}",
            "response = requests.post(url, json=payload, headers=headers, timeout=120)",
            "response.raise_for_status()",
            "print(response.json())",
        ]),
    },
    {
        "id": "faster-whisper-stt",
        "name": "Speech to Text",
        "provider": "Faster Whisper",
        "category": "Audio",
        "method": "POST",
        "local_endpoint": "/api/stt",
        "upstream_endpoint": f"{GATEWAY_BASE}/stt/v1/audio/transcriptions",
        "summary": "Upload audio and receive a JSON transcription using Faster Whisper REST via the gateway.",
        "inputs": [
            {"field": "file", "type": "file", "description": "Audio file (WAV/MP3/FLAC)."}
        ],
        "notes": [
            "Server responds with the OpenAI transcription schema.",
            "Large files take longer; check logs on the STT container if requests time out."
        ],
        "sample_payload": {
            "file": "@sample.wav"
        },
        "form_defaults": {},
        "curl_example": "\n".join([
            "curl -X POST \\",
            f"  {GATEWAY_BASE}/stt/v1/audio/transcriptions \\",
            "  -H 'Accept: application/json' \\",
            "  -H 'X-API-Key: YOUR_DASHBOARD_API_KEY' \\",
            "  -F 'file=@sample.wav'"
        ]),
        "python_example": "\n".join([
            "import requests",
            "",
            f"url = \"{GATEWAY_BASE}/stt/v1/audio/transcriptions\"",
            "headers = {\"X-API-Key\": \"YOUR_DASHBOARD_API_KEY\"}",
            "with open(\"sample.wav\", \"rb\") as audio:",
                "    files = {\"file\": (\"sample.wav\", audio, \"audio/wav\")}",
                "    response = requests.post(url, headers=headers, files=files, timeout=120)",
            "response.raise_for_status()",
            "print(response.json())",
        ]),
    }
]


def _parse_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: Any) -> int | None:
    if value in (None, "", "-"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_api_key(key: str | None) -> str:
    if not key or key == "-":
        return "(none)"
    return key


def _primary_client_ip(remote_addr: str | None, forwarded_for: str | None) -> str:
    if forwarded_for and forwarded_for != "-":
        for part in forwarded_for.split(","):
            candidate = part.strip()
            if candidate:
                return candidate
    return remote_addr or "-"


def _classify_network_scope(ip_str: str) -> str:
    try:
        ip_obj = ip_address(ip_str)
    except ValueError:
        return "Unknown"
    if ip_obj.is_loopback:
        return "Loopback"
    if ip_obj.is_private:
        return "Private"
    if ip_obj.is_reserved or ip_obj.is_multicast:
        return "Reserved"
    return "Public"


def _mark_suspicious(entry: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    status = entry["status"]
    uri = entry["request_uri"]
    if status >= 500:
        labels.append("upstream_error")
    elif status >= 400:
        labels.append("client_error")

    if entry["api_key"] == "(none)":
        labels.append("no_api_key")

    lower_uri = uri.lower()
    for hint in SUSPICIOUS_PATH_HINTS:
        if hint in lower_uri:
            labels.append("suspicious_path")
            break

    if entry["request_time_ms"] and entry["request_time_ms"] > 15000:
        labels.append("very_slow")

    return labels


def _append_ignore_clients_clause(clauses: list[str], params: list[Any]) -> None:
    if not MONITORING_IGNORE_CLIENTS:
        return
    placeholders = ", ".join("?" for _ in MONITORING_IGNORE_CLIENTS)
    clauses.append(f"client_ip NOT IN ({placeholders})")
    params.extend(MONITORING_IGNORE_CLIENTS)


def monitoring_filters_metadata() -> dict[str, Any]:
    return {
        "active": MONITORING_FILTERS_ACTIVE,
        "ignored_clients": list(MONITORING_IGNORE_CLIENTS),
        "ignored_client_count": len(MONITORING_IGNORE_CLIENTS),
    }


def ensure_monitoring_storage() -> None:
    """Create SQLite storage and indexes if missing."""
    MONITORING_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(MONITORING_DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS access_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                remote_addr TEXT,
                forwarded_for TEXT,
                client_ip TEXT,
                network_scope TEXT,
                request_method TEXT,
                request_uri TEXT,
                request_path TEXT,
                status INTEGER,
                status_family TEXT,
                request_time_ms INTEGER,
                body_bytes_sent INTEGER,
                bytes_sent INTEGER,
                api_key TEXT,
                referer TEXT,
                user_agent TEXT,
                upstream_addr TEXT,
                upstream_status TEXT,
                upstream_response_time_ms INTEGER,
                flags TEXT,
                is_flagged INTEGER
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_access_events_timestamp ON access_events(timestamp)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_access_events_client ON access_events(client_ip)"
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_access_events_identity
            ON access_events(timestamp, client_ip, request_method, request_uri, status, api_key)
            """
        )


def get_db_connection() -> sqlite3.Connection:
    ensure_monitoring_storage()
    conn = sqlite3.connect(MONITORING_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_ingest_state() -> dict[str, Any]:
    if not MONITORING_STATE_PATH.exists():
        return {}
    try:
        return json.loads(MONITORING_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_ingest_state(state: dict[str, Any]) -> None:
    MONITORING_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    MONITORING_STATE_PATH.write_text(json.dumps(state), encoding="utf-8")


def parse_combined_log_line(text: str) -> dict[str, Any] | None:
    match = COMBINED_LOG_RE.match(text)
    if not match:
        return None

    request = match.group("request") or ""
    request_parts = request.split()
    method = request_parts[0] if request_parts else "-"
    uri = request_parts[1] if len(request_parts) > 1 else "-"

    time_str = match.group("time")
    try:
        parsed_time = datetime.strptime(time_str, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None

    body_bytes_sent = match.group("body_bytes_sent")
    if body_bytes_sent == "-" or body_bytes_sent is None:
        body_bytes_sent = "0"

    return {
        "time": parsed_time.astimezone(timezone.utc).isoformat(),
        "remote_addr": match.group("remote_addr"),
        "forwarded_for": "-",
        "request_method": method,
        "request_uri": uri,
        "status": match.group("status"),
        "request_time": "0",
        "body_bytes_sent": body_bytes_sent,
        "bytes_sent": body_bytes_sent,
        "http_referer": match.group("http_referer") or "-",
        "user_agent": match.group("user_agent") or "-",
        "api_key": "-",
        "upstream_addr": "-",
        "upstream_status": "-",
        "upstream_response_time": None,
    }


def parse_log_line(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return None
    return parse_combined_log_line(stripped)


def parse_log_entry(raw: dict[str, Any]) -> dict[str, Any] | None:
    timestamp_raw = raw.get("time")
    if not timestamp_raw:
        return None
    try:
        timestamp = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
    except ValueError:
        return None

    request_method = raw.get("request_method", "-")
    request_uri = raw.get("request_uri", "-")
    status = _parse_int(raw.get("status")) or 0
    request_time = _parse_float(raw.get("request_time")) or 0.0
    upstream_response_time = _parse_float(raw.get("upstream_response_time"))

    forwarded_for = raw.get("forwarded_for", "-")
    remote_addr = raw.get("remote_addr", "-")
    client_ip = _primary_client_ip(remote_addr, forwarded_for)
    network_scope = _classify_network_scope(client_ip)

    api_key = _normalize_api_key(raw.get("api_key"))
    upstream_status_str = raw.get("upstream_status", "-")
    upstream_status = _parse_int(upstream_status_str)

    entry: dict[str, Any] = {
        "timestamp": timestamp,
        "remote_addr": remote_addr,
        "forwarded_for": forwarded_for.split(",") if forwarded_for not in ("", "-") else [],
        "client_ip": client_ip,
        "network_scope": network_scope,
        "request_method": request_method,
        "request_uri": request_uri,
        "request_path": request_uri.split("?")[0],
        "status": status,
        "status_family": f"{status // 100}xx",
        "request_time_ms": int(request_time * 1000),
        "body_bytes_sent": _parse_int(raw.get("body_bytes_sent")) or 0,
        "bytes_sent": _parse_int(raw.get("bytes_sent")) or 0,
        "api_key": api_key,
        "referer": raw.get("http_referer", "-"),
        "user_agent": raw.get("user_agent", "-"),
        "upstream_addr": raw.get("upstream_addr", "-"),
        "upstream_status": upstream_status if upstream_status is not None else upstream_status_str,
        "upstream_response_time_ms": (
            int(upstream_response_time * 1000) if upstream_response_time is not None else None
        ),
    }
    labels = _mark_suspicious(entry)
    entry["flags"] = labels
    entry["is_flagged"] = bool(labels)
    return entry


def sync_log_to_database() -> None:
    """Ingest new nginx access log lines into SQLite storage."""
    if not NGINX_ACCESS_LOG.exists():
        return

    with INGEST_LOCK:
        try:
            stat = NGINX_ACCESS_LOG.stat()
        except FileNotFoundError:
            return

        state = load_ingest_state()
        position = int(state.get("position", 0))
        inode = state.get("inode")

        if inode is not None and inode != stat.st_ino:
            position = 0
        if stat.st_size < position:
            position = 0

        new_position = position
        parsed_entries: list[dict[str, Any]] = []
        try:
            with NGINX_ACCESS_LOG.open("r", encoding="utf-8") as handle:
                handle.seek(position)
                for line in handle:
                    raw = parse_log_line(line)
                    if not raw:
                        continue
                    entry = parse_log_entry(raw)
                    if not entry:
                        continue
                    parsed_entries.append(entry)
                new_position = handle.tell()
        except FileNotFoundError:
            return

        if not parsed_entries:
            save_ingest_state({"position": new_position, "inode": stat.st_ino})
            return

        with get_db_connection() as conn:
            for entry in parsed_entries:
                forwarded_serialised = json.dumps(entry["forwarded_for"])
                flags_serialised = json.dumps(entry["flags"])
                upstream_status = entry["upstream_status"]
                if isinstance(upstream_status, (list, tuple)):
                    upstream_status = ",".join(str(value) for value in upstream_status)
                elif upstream_status is not None:
                    upstream_status = str(upstream_status)

                conn.execute(
                    """
                    INSERT OR IGNORE INTO access_events (
                        timestamp,
                        remote_addr,
                        forwarded_for,
                        client_ip,
                        network_scope,
                        request_method,
                        request_uri,
                        request_path,
                        status,
                        status_family,
                        request_time_ms,
                        body_bytes_sent,
                        bytes_sent,
                        api_key,
                        referer,
                        user_agent,
                        upstream_addr,
                        upstream_status,
                        upstream_response_time_ms,
                        flags,
                        is_flagged
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry["timestamp"].isoformat(),
                        entry["remote_addr"],
                        forwarded_serialised,
                        entry["client_ip"],
                        entry["network_scope"],
                        entry["request_method"],
                        entry["request_uri"],
                        entry["request_path"],
                        entry["status"],
                        entry["status_family"],
                        entry["request_time_ms"],
                        entry["body_bytes_sent"],
                        entry["bytes_sent"],
                        entry["api_key"],
                        entry["referer"],
                        entry["user_agent"],
                        entry["upstream_addr"],
                        upstream_status,
                        entry["upstream_response_time_ms"],
                        flags_serialised,
                        1 if entry["is_flagged"] else 0,
                    ),
                )

            if MONITORING_MAX_AGE_DAYS > 0:
                cutoff = datetime.now(timezone.utc) - timedelta(days=MONITORING_MAX_AGE_DAYS)
                conn.execute(
                    "DELETE FROM access_events WHERE timestamp < ?",
                    (cutoff.isoformat(),),
                )
            conn.commit()

        save_ingest_state({"position": new_position, "inode": stat.st_ino})


def row_to_entry(row: sqlite3.Row) -> dict[str, Any]:
    timestamp = datetime.fromisoformat(row["timestamp"])
    forwarded_raw = row["forwarded_for"] or "[]"
    try:
        forwarded_for = json.loads(forwarded_raw)
    except json.JSONDecodeError:
        forwarded_for = []

    flags_raw = row["flags"] or "[]"
    try:
        flags = json.loads(flags_raw)
    except json.JSONDecodeError:
        flags = []

    upstream_status_value = row["upstream_status"]
    try:
        upstream_status = int(upstream_status_value) if upstream_status_value is not None else None
    except (TypeError, ValueError):
        upstream_status = upstream_status_value

    status = int(row["status"]) if row["status"] is not None else 0
    request_time_ms = row["request_time_ms"] if row["request_time_ms"] is not None else 0
    body_bytes_sent = row["body_bytes_sent"] if row["body_bytes_sent"] is not None else 0
    bytes_sent = row["bytes_sent"] if row["bytes_sent"] is not None else 0

    entry = {
        "timestamp": timestamp,
        "remote_addr": row["remote_addr"],
        "forwarded_for": forwarded_for,
        "client_ip": row["client_ip"],
        "network_scope": row["network_scope"],
        "request_method": row["request_method"],
        "request_uri": row["request_uri"],
        "request_path": row["request_path"],
        "status": status,
        "status_family": row["status_family"],
        "request_time_ms": request_time_ms,
        "body_bytes_sent": body_bytes_sent,
        "bytes_sent": bytes_sent,
        "api_key": row["api_key"],
        "referer": row["referer"],
        "user_agent": row["user_agent"],
        "upstream_addr": row["upstream_addr"],
        "upstream_status": upstream_status,
        "upstream_response_time_ms": row["upstream_response_time_ms"],
        "flags": flags,
        "is_flagged": bool(row["is_flagged"]),
    }
    return entry


def load_log_entries(
    limit: int | None = None,
    since: datetime | None = None,
    *,
    ignore_clients: bool = True,
) -> list[dict[str, Any]]:
    sync_log_to_database()
    query = "SELECT * FROM access_events"
    clauses: list[str] = []
    params: list[Any] = []

    if since is not None:
        clauses.append("timestamp >= ?")
        params.append(since.isoformat())

    if ignore_clients:
        _append_ignore_clients_clause(clauses, params)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY timestamp DESC"

    effective_limit: int | None
    if limit is not None:
        effective_limit = limit
    elif since is None and MONITORING_MAX_SCAN:
        effective_limit = MONITORING_MAX_SCAN
    else:
        effective_limit = None

    if effective_limit is not None:
        query += " LIMIT ?"
        params.append(effective_limit)

    with get_db_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    entries = [row_to_entry(row) for row in rows]
    entries.reverse()
    if limit is not None and len(entries) > limit:
        entries = entries[-limit:]
    return entries


def count_log_entries(since: datetime | None = None, *, ignore_clients: bool = True) -> int:
    sync_log_to_database()
    query = "SELECT COUNT(*) AS total FROM access_events"
    clauses: list[str] = []
    params: list[Any] = []
    if since is not None:
        clauses.append("timestamp >= ?")
        params.append(since.isoformat())
    if ignore_clients:
        _append_ignore_clients_clause(clauses, params)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    with get_db_connection() as conn:
        row = conn.execute(query, params).fetchone()
    if row is None:
        return 0
    if isinstance(row, sqlite3.Row):
        return int(row["total"])
    return int(row[0])


def summarise_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not entries:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "log_path": str(NGINX_ACCESS_LOG),
            "totals": {
                "requests": 0,
                "unique_clients": 0,
                "unique_api_keys": 0,
                "flagged_requests": 0,
                "unique_user_agents": 0,
            },
            "status_families": {},
            "top_clients": [],
            "top_api_keys": [],
            "top_endpoints": [],
            "top_user_agents": [],
            "requests_per_minute": [],
            "alerts": [],
            "time_window": None,
        }

    entries_sorted = sorted(entries, key=lambda item: item["timestamp"])
    start_ts = entries_sorted[0]["timestamp"]
    end_ts = entries_sorted[-1]["timestamp"]

    unique_clients = {}
    unique_api_keys = Counter()
    top_endpoints_counter = Counter()
    status_family_counter = Counter()
    flagged_count = 0
    user_agent_counter = Counter()

    per_minute = defaultdict(int)
    recent_window_since = end_ts - timedelta(minutes=MONITORING_ALERT_WINDOW_MIN)
    recent_client_errors = Counter()
    recent_missing_keys = Counter()
    recent_volume = Counter()
    alerts: list[dict[str, Any]] = []

    for entry in entries_sorted:
        client = entry["client_ip"]
        unique_clients.setdefault(
            client,
            {
                "client": client,
                "network_scope": entry["network_scope"],
                "first_seen": entry["timestamp"],
                "last_seen": entry["timestamp"],
                "count": 0,
            },
        )
        unique_clients[client]["last_seen"] = entry["timestamp"]
        unique_clients[client]["count"] += 1

        unique_api_keys[entry["api_key"]] += 1
        top_endpoints_counter[entry["request_path"]] += 1
        status_family_counter[entry["status_family"]] += 1
        user_agent = entry["user_agent"] or "(unknown)"
        user_agent_counter[user_agent] += 1

        bucket = entry["timestamp"].replace(second=0, microsecond=0).isoformat()
        per_minute[bucket] += 1

        if entry["is_flagged"]:
            flagged_count += 1

        if entry["timestamp"] >= recent_window_since:
            recent_volume[client] += 1
            if "client_error" in entry["flags"]:
                recent_client_errors[client] += 1
            if "no_api_key" in entry["flags"]:
                recent_missing_keys[client] += 1

    for client, count in recent_client_errors.items():
        if count >= ALERT_CLIENT_ERROR_THRESHOLD:
            alerts.append(
                {
                    "level": "warning",
                    "type": "excessive_client_errors",
                    "message": f"{count} client errors from {client} in the last {MONITORING_ALERT_WINDOW_MIN} minutes.",
                    "client": client,
                    "count": count,
                    "window_minutes": MONITORING_ALERT_WINDOW_MIN,
                }
            )

    for client, count in recent_volume.items():
        if count >= ALERT_RATE_THRESHOLD:
            alerts.append(
                {
                    "level": "warning",
                    "type": "high_request_rate",
                    "message": f"{client} made {count} requests in the last {MONITORING_ALERT_WINDOW_MIN} minutes.",
                    "client": client,
                    "count": count,
                    "window_minutes": MONITORING_ALERT_WINDOW_MIN,
                }
            )

    missing_key_total = sum(recent_missing_keys.values())
    if missing_key_total >= ALERT_MISSING_KEY_THRESHOLD:
        alerts.append(
            {
                "level": "info",
                "type": "missing_api_keys",
                "message": f"{missing_key_total} recent requests without API keys detected.",
                "count": missing_key_total,
                "window_minutes": MONITORING_ALERT_WINDOW_MIN,
            }
        )

    top_clients = sorted(unique_clients.values(), key=lambda item: item["count"], reverse=True)[:5]
    for client in top_clients:
        client["first_seen"] = client["first_seen"].isoformat()
        client["last_seen"] = client["last_seen"].isoformat()

    top_api_keys = unique_api_keys.most_common(5)
    top_api_keys = [
        {"api_key": api_key, "count": count, "is_anonymous": api_key == "(none)"}
        for api_key, count in top_api_keys
    ]

    top_endpoints = [
        {"endpoint": endpoint, "count": count}
        for endpoint, count in top_endpoints_counter.most_common(5)
    ]

    top_user_agents = [
        {"user_agent": agent, "count": count}
        for agent, count in user_agent_counter.most_common(5)
    ]

    status_families = dict(status_family_counter)
    requests_per_minute = sorted(
        [{"bucket": bucket, "count": count} for bucket, count in per_minute.items()],
        key=lambda item: item["bucket"],
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "log_path": str(NGINX_ACCESS_LOG),
        "totals": {
            "requests": len(entries_sorted),
            "unique_clients": len(unique_clients),
            "unique_api_keys": len(unique_api_keys),
            "flagged_requests": flagged_count,
            "unique_user_agents": len(user_agent_counter),
        },
        "status_families": status_families,
        "top_clients": top_clients,
        "top_api_keys": top_api_keys,
        "top_endpoints": top_endpoints,
        "top_user_agents": top_user_agents,
        "requests_per_minute": requests_per_minute,
        "alerts": alerts,
        "time_window": {
            "start": start_ts.isoformat(),
            "end": end_ts.isoformat(),
            "minutes": max(int((end_ts - start_ts).total_seconds() // 60), 0),
        },
    }


def serialise_entry(entry: dict[str, Any]) -> dict[str, Any]:
    payload = dict(entry)
    payload["timestamp"] = entry["timestamp"].isoformat()
    return payload


def check_service_health(service: dict) -> tuple[bool, int | None, str]:
    """Perform a lightweight reachability check against the service gateway target."""
    endpoint = service.get("upstream_endpoint")
    if not endpoint:
        return False, None, "Missing upstream endpoint"

    response = None
    headers = gateway_headers()
    try:
        response = requests.request("HEAD", endpoint, headers=headers, timeout=5)
    except Exception:
        try:
            response = requests.get(endpoint, headers=headers, timeout=5)
        except Exception as exc:
            return False, None, str(exc)

    if response is None:
        return False, None, "No response"

    status = response.status_code
    detail = response.reason or f"HTTP {status}"

    ok = status < 500 and status not in (404,)
    if status in (401, 403, 405, 415):
        ok = True

    return ok, status, detail


def fetch_json(url: str, headers: dict | None = None, timeout: int = 10) -> dict:
    response = requests.get(url, headers=gateway_headers(headers), timeout=timeout)
    response.raise_for_status()
    return response.json()


def info_lmstudio_models() -> dict:
    data = fetch_json(f"{GATEWAY_BASE}/lmstudio/v1/models")
    models = data.get("data") or data.get("models") or []
    return {"count": len(models), "models": models}


def info_openwebui_models() -> dict:
    headers = {}
    if OPENWEBUI_API_KEY:
        headers["Authorization"] = f"Bearer {OPENWEBUI_API_KEY}"
    endpoints = [
        f"{GATEWAY_BASE}/openwebui/api/models",
        f"{GATEWAY_BASE}/openwebui/api/chat/models",
    ]
    last_error: Exception | None = None
    for endpoint in endpoints:
        try:
            data = fetch_json(endpoint, headers=headers)
        except Exception as exc:  # noqa: BLE001 - bubble the last error if all fail
            last_error = exc
            continue
        models = data.get("models") or data.get("data") or []
        return {"endpoint": endpoint, "count": len(models), "models": models}
    if last_error:
        raise last_error
    return {"count": 0, "models": []}


def info_ollama_models() -> dict:
    data = fetch_json(f"{GATEWAY_BASE}/ollama/api/tags")
    models = data.get("models", [])
    return {"count": len(models), "models": models}


def info_kokoro_voices() -> dict:
    endpoints = [
        f"{GATEWAY_BASE}/kokoro/v1/voices",
        f"{GATEWAY_BASE}/kokoro/voices",
    ]
    last_error: Exception | None = None
    for endpoint in endpoints:
        try:
            data = fetch_json(endpoint)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
        voices = data.get("voices") if isinstance(data, dict) else data
        if isinstance(voices, dict):
            entries = voices.get("voices") or voices.get("data") or []
        else:
            entries = voices if isinstance(voices, list) else []
        return {
            "endpoint": endpoint,
            "count": len(entries),
            "voices": entries or voices,
        }
    if last_error:
        raise last_error
    return {"count": 0, "voices": []}


def info_faster_whisper_models() -> dict:
    data = fetch_json(f"{GATEWAY_BASE}/stt/v1/models")
    models = data.get("data") or data.get("models") or []
    return {"count": len(models), "models": models}


SERVICE_INFO_HANDLERS: dict[str, Callable[[], dict]] = {
    "lmstudio-chat": info_lmstudio_models,
    "lmstudio-models": info_lmstudio_models,
    "lmstudio-responses": info_lmstudio_models,
    "lmstudio-completions": info_lmstudio_models,
    "lmstudio-embeddings": info_lmstudio_models,
    "openwebui-chat": info_openwebui_models,
    "gateway-ollama-chat": info_ollama_models,
    "kokoro-tts": info_kokoro_voices,
    "faster-whisper-stt": info_faster_whisper_models,
}


async def require_api_key(request: Request) -> None:
    if not DASHBOARD_API_KEYS:
        return
    header_key = request.headers.get("x-api-key")
    query_key = request.query_params.get("api_key")
    provided = header_key or query_key
    if provided and provided in DASHBOARD_API_KEYS:
        return
    raise HTTPException(status_code=401, detail="Invalid or missing API key")

# -- APPLICATION SETUP
app = FastAPI(title="AI Hub Dashboard")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))

# -- ROUTES for UI
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the main dashboard page."""
    template = env.get_template("index.html")
    return template.render(
        ip=AIHUB_IP,
        ports=PORTS,
        services=SERVICES,
        static_version=STATIC_VERSION,
    )


@app.get("/api/services", response_class=JSONResponse)
async def list_services(_: None = Depends(require_api_key)):
    """Expose service metadata for frontend or external tools."""
    return {
        "ip": AIHUB_IP,
        "ports": PORTS,
        "services": SERVICES,
    }


@app.get("/api/service-status", response_class=JSONResponse)
async def service_status(_: None = Depends(require_api_key)):
    """Return reachability status for each configured service."""
    results = {}
    for service in SERVICES:
        ok, status, detail = check_service_health(service)
        results[service["id"]] = {
            "ok": ok,
            "status": status,
            "detail": detail,
        }
    return {"statuses": results}


@app.get("/api/auth/verify", response_class=JSONResponse)
async def auth_verify(_: None = Depends(require_api_key)):
    """Auth probe used by the nginx gateway to validate API keys."""
    return {"ok": True}


@app.get("/api/service-info/{service_id}", response_class=JSONResponse)
async def service_info(service_id: str, _: None = Depends(require_api_key)):
    """Return gateway-backed live data for a given service."""
    handler = SERVICE_INFO_HANDLERS.get(service_id)
    if not handler:
        raise HTTPException(status_code=404, detail="No live data available for this service.")
    try:
        data = handler()
    except requests.HTTPError as exc:
        response = exc.response
        status_code = response.status_code if response is not None else 502
        detail = response.text if response is not None else str(exc)
        raise HTTPException(status_code=status_code, detail=detail[:400]) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"data": data}


@app.get("/api/monitoring/summary", response_class=JSONResponse)
async def monitoring_summary(limit: int = MONITORING_MAX_SCAN, _: None = Depends(require_api_key)):
    """Return aggregated monitoring data derived from nginx access logs."""
    limit = max(10, min(limit, MONITORING_MAX_SCAN))
    entries = load_log_entries(limit=limit)
    summary = summarise_entries(entries)
    filters_meta = monitoring_filters_metadata()
    summary["filters"] = filters_meta
    summary["ignored_clients"] = filters_meta["ignored_clients"]
    return summary


@app.get("/api/monitoring/events", response_class=JSONResponse)
async def monitoring_events(
    limit: int = MONITORING_DEFAULT_LIMIT,
    minutes: int | None = None,
    _: None = Depends(require_api_key),
):
    """Return recent gateway access events."""
    limit = max(10, min(limit, MONITORING_MAX_SCAN))
    since_dt: datetime | None = None
    window_minutes: int | None = None
    if minutes is not None:
        window_minutes = max(1, min(minutes, MONITORING_ALERT_WINDOW_MIN * 4))
        since_dt = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

    fetch_limit = None
    if limit is not None:
        fetch_limit = limit + 1

    raw_entries = load_log_entries(limit=fetch_limit, since=since_dt)
    if limit is not None and len(raw_entries) > limit:
        entries = raw_entries[-limit:]
        truncated = True
    else:
        entries = raw_entries
        truncated = False

    filters_meta = monitoring_filters_metadata()
    total_filtered = count_log_entries(since_dt)
    total_raw = total_filtered
    if filters_meta["active"]:
        total_raw = count_log_entries(since_dt, ignore_clients=False)
    ignored_request_count = max(total_raw - total_filtered, 0)

    response: dict[str, Any] = {
        "limit": limit,
        "count": len(entries),
        "total": total_filtered,
        "total_including_ignored": total_raw,
        "ignored_request_count": ignored_request_count,
        "window_minutes": window_minutes,
        "since": since_dt.isoformat() if since_dt else None,
        "truncated": truncated or total_filtered >= MONITORING_MAX_SCAN,
        "events": [serialise_entry(entry) for entry in entries],
        "filters": filters_meta,
        "ignored_clients": filters_meta["ignored_clients"],
    }
    if ignored_request_count > 0 and len(entries) == 0:
        response["empty_message"] = "Only ignored clients made requests during this window."
    return response


# -- API ROUTES for agent/service calls
@app.post("/api/chat")
async def chat(model: str = Form(...), message: str = Form(...), _: None = Depends(require_api_key)):
    """Send a chat request to LM Studio."""
    url = f"{GATEWAY_BASE}/lmstudio/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "stream": False
    }
    try:
        r = requests.post(url, json=payload, headers=gateway_headers(), timeout=120)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat request failed: {e}")
    return JSONResponse(content={"status": r.status_code, "response": r.json()})


@app.post("/api/lmstudio/models")
async def list_models(_: None = Depends(require_api_key)):
    """List models currently hosted on LM Studio."""
    url = f"{GATEWAY_BASE}/lmstudio/v1/models"
    try:
        r = requests.get(url, headers=gateway_headers(), timeout=10)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model listing failed: {e}")
    return JSONResponse(content={"status": r.status_code, "response": r.json()})

@app.post("/api/lmstudio/responses")
async def lmstudio_responses(model: str = Form(...), prompt: str = Form(...), _: None = Depends(require_api_key)):
    """Proxy the LM Studio Responses endpoint."""
    url = f"{GATEWAY_BASE}/lmstudio/v1/responses"
    payload = {
        "model": model,
        "input": prompt,
    }
    try:
        r = requests.post(url, json=payload, headers=gateway_headers(), timeout=120)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LM Studio responses failed: {e}")
    return JSONResponse(content={"status": r.status_code, "response": r.json()})

@app.post("/api/lmstudio/completions")
async def lmstudio_completions(model: str = Form(...), prompt: str = Form(...), max_tokens: str = Form(""), _: None = Depends(require_api_key)):
    """Proxy the OpenAI-compatible Completions endpoint."""
    url = f"{GATEWAY_BASE}/lmstudio/v1/completions"
    payload = {
        "model": model,
        "prompt": prompt,
    }
    max_tokens_value = None
    if max_tokens:
        try:
            max_tokens_value = int(max_tokens)
        except ValueError:
            raise HTTPException(status_code=400, detail="max_tokens must be an integer")
    if max_tokens_value is not None:
        payload["max_tokens"] = max_tokens_value

    try:
        r = requests.post(url, json=payload, headers=gateway_headers(), timeout=120)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LM Studio completions failed: {e}")
    return JSONResponse(content={"status": r.status_code, "response": r.json()})

@app.post("/api/lmstudio/embeddings")
async def lmstudio_embeddings(model: str = Form(...), text: str = Form(...), _: None = Depends(require_api_key)):
    """Proxy the embeddings endpoint to generate vectors."""
    url = f"{GATEWAY_BASE}/lmstudio/v1/embeddings"
    payload = {
        "model": model,
        "input": text,
    }
    try:
        r = requests.post(url, json=payload, headers=gateway_headers(), timeout=60)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LM Studio embeddings failed: {e}")
    return JSONResponse(content={"status": r.status_code, "response": r.json()})

@app.post("/api/tts")
async def tts(text: str = Form(...), voice: str = Form("af_bella"), _: None = Depends(require_api_key)):
    """Generate TTS via Kokoro, save locally and return playback path."""
    url = f"{GATEWAY_BASE}/kokoro/v1/audio/speech"
    payload = {
        "model": "kokoro",
        "input": text,
        "voice": voice,
        "response_format": "mp3",
        "speed": 1.0
    }
    try:
        r = requests.post(url, json=payload, headers=gateway_headers(), timeout=20)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS request failed: {e}")

    out_dir = STATIC_DIR / "tts_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"tts_{int(time.time())}.mp3"
    file_path = out_dir / filename

    with open(file_path, "wb") as f:
        f.write(r.content)

    return JSONResponse(
        content={
            "status": r.status_code,
            "audio": f"/static/tts_outputs/{filename}",
            "filename": filename,
            "voice": voice,
        }
    )

@app.post("/api/stt")
async def stt(file: UploadFile = File(...), _: None = Depends(require_api_key)):
    """Upload a WAV/MP3 file and transcribe via Faster-Whisper REST."""
    url = f"{GATEWAY_BASE}/stt/v1/audio/transcriptions"
    try:
        files = {"file": (file.filename, file.file, file.content_type)}
        r = requests.post(url, files=files, headers=gateway_headers(), timeout=30)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT request failed: {e}")

    return JSONResponse(content={"status": r.status_code, "response": r.json()})


@app.post("/api/openwebui/chat")
async def openwebui_chat(model: str = Form(...), message: str = Form(...), _: None = Depends(require_api_key)):
    """Send a chat completion request through Open WebUI."""
    url = f"{GATEWAY_BASE}/openwebui/api/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
    }
    headers = {}
    if OPENWEBUI_API_KEY:
        headers["Authorization"] = f"Bearer {OPENWEBUI_API_KEY}"

    try:
        r = requests.post(url, json=payload, headers=gateway_headers(headers), timeout=15)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Open WebUI chat failed: {e}")
    return JSONResponse(content={"status": r.status_code, "response": r.json()})


@app.post("/api/gateway/chat")
async def gateway_chat(model: str = Form(...), message: str = Form(...), _: None = Depends(require_api_key)):
    """Relay chat completions through the nginx gateway."""
    url = f"{GATEWAY_BASE}/lmstudio/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "stream": False,
    }
    try:
        r = requests.post(url, json=payload, headers=gateway_headers(), timeout=120)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gateway chat failed: {e}")
    return JSONResponse(content={"status": r.status_code, "response": r.json()})


@app.post("/api/gateway/ollama/chat")
async def gateway_ollama_chat(model: str = Form(...), message: str = Form(...), _: None = Depends(require_api_key)):
    """Relay chat completions to Ollama through the nginx gateway."""
    url = f"{GATEWAY_BASE}/ollama/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "stream": False,
    }
    try:
        r = requests.post(url, json=payload, headers=gateway_headers(), timeout=120)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gateway Ollama chat failed: {e}")
    return JSONResponse(content={"status": r.status_code, "response": r.json()})
