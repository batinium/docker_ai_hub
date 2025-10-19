# ~/aihub/dashboard/app.py

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from typing import Callable
import requests, os, time

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
STATIC_VERSION = os.environ.get("STATIC_VERSION") or str(int(time.time()))
GATEWAY_BASE = f"http://{AIHUB_IP}:{GATEWAY_PORT}"
OPENWEBUI_API_KEY = os.environ.get("OPENWEBUI_API_KEY")
DASHBOARD_API_KEYS = [
    key.strip()
    for key in os.environ.get("DASHBOARD_API_KEYS", "").split(",")
    if key.strip()
]

PORTS = {
    "lmstudio": LMSTUDIO_PORT,
    "kokoro": KOKORO_PORT,
    "stt": STT_REST_PORT,
    "openwebui": OPENWEBUI_PORT,
    "gateway": GATEWAY_PORT,
}

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
            "model": "openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix@q5_1",
            "messages": [{"role": "user", "content": "Hello, AI Hub!"}],
            "stream": False
        },
        "form_defaults": {
            "model": "openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix@q5_1",
            "message": "What tools are available on AI Hub right now?"
        },
        "curl_example": "\n".join([
            "curl -X POST \\",
            f"  {GATEWAY_BASE}/lmstudio/v1/chat/completions \\",
            "  -H 'Content-Type: application/json' \\",
            "  -d '{\"model\":\"openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix@q5_1\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello, AI Hub!\"}],\"stream\":false}'"
        ]),
        "python_example": "\n".join([
            "import requests",
            "",
            f"url = \"{GATEWAY_BASE}/lmstudio/v1/chat/completions\"",
            "payload = {",
            "    \"model\": \"openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix@q5_1\",",
            "    \"messages\": [{\"role\": \"user\", \"content\": \"Hello, AI Hub!\"}],",
            "    \"stream\": False",
            "}",
            "response = requests.post(url, json=payload, timeout=60)",
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
            f"  {GATEWAY_BASE}/lmstudio/v1/models"
        ]),
        "python_example": "\n".join([
            "import requests",
            "",
            f"url = \"{GATEWAY_BASE}/lmstudio/v1/models\"",
            "response = requests.get(url, timeout=30)",
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
            "model": "openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix@q5_1",
            "input": "Briefly describe the AI Hub architecture."
        },
        "form_defaults": {
            "model": "openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix@q5_1",
            "prompt": "Briefly describe the AI Hub architecture."
        },
        "curl_example": "\n".join([
            "curl -X POST \\",
            f"  {GATEWAY_BASE}/lmstudio/v1/responses \\",
            "  -H 'Content-Type: application/json' \\",
            "  -d '{\"model\":\"openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix@q5_1\",\"input\":\"Briefly describe the AI Hub architecture.\"}'"
        ]),
        "python_example": "\n".join([
            "import requests",
            "",
            f"url = \"{GATEWAY_BASE}/lmstudio/v1/responses\"",
            "payload = {",
            "    \"model\": \"openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix@q5_1\",",
            "    \"input\": \"Briefly describe the AI Hub architecture.\"",
            "}",
            "response = requests.post(url, json=payload, timeout=60)",
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
            "model": "openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix@q5_1",
            "prompt": "Write a short promotional slogan for AI Hub:",
            "max_tokens": 120
        },
        "form_defaults": {
            "model": "openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix@q5_1",
            "prompt": "Write a short promotional slogan for AI Hub:",
            "max_tokens": "120"
        },
        "curl_example": "\n".join([
            "curl -X POST \\",
            f"  {GATEWAY_BASE}/lmstudio/v1/completions \\",
            "  -H 'Content-Type: application/json' \\",
            "  -d '{\"model\":\"openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix@q5_1\",\"prompt\":\"Write a short promotional slogan for AI Hub:\",\"max_tokens\":120}'"
        ]),
        "python_example": "\n".join([
            "import requests",
            "",
            f"url = \"{GATEWAY_BASE}/lmstudio/v1/completions\"",
            "payload = {",
            "    \"model\": \"openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix@q5_1\",",
            "    \"prompt\": \"Write a short promotional slogan for AI Hub:\",",
            "    \"max_tokens\": 120",
            "}",
            "response = requests.post(url, json=payload, timeout=60)",
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
            "response = requests.post(url, json=payload, timeout=60)",
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
            "response = requests.post(url, json=payload, timeout=60)",
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
            "headers = {\"Authorization\": \"Bearer YOUR_OPENWEBUI_KEY\"}",
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
            "response = requests.post(url, json=payload, timeout=120)",
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
            "  -F 'file=@sample.wav'"
        ]),
        "python_example": "\n".join([
            "import requests",
            "",
            f"url = \"{GATEWAY_BASE}/stt/v1/audio/transcriptions\"",
            "with open(\"sample.wav\", \"rb\") as audio:",
            "    files = {\"file\": (\"sample.wav\", audio, \"audio/wav\")}",
            "    response = requests.post(url, files=files, timeout=120)",
            "response.raise_for_status()",
            "print(response.json())",
        ]),
    }
]


def check_service_health(service: dict) -> tuple[bool, int | None, str]:
    """Perform a lightweight reachability check against the service gateway target."""
    endpoint = service.get("upstream_endpoint")
    if not endpoint:
        return False, None, "Missing upstream endpoint"

    response = None
    try:
        response = requests.request("HEAD", endpoint, timeout=5)
    except Exception:
        try:
            response = requests.get(endpoint, timeout=5)
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
    response = requests.get(url, headers=headers, timeout=timeout)
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
        r = requests.post(url, json=payload, timeout=120)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat request failed: {e}")
    return JSONResponse(content={"status": r.status_code, "response": r.json()})


@app.post("/api/lmstudio/models")
async def list_models(_: None = Depends(require_api_key)):
    """List models currently hosted on LM Studio."""
    url = f"{GATEWAY_BASE}/lmstudio/v1/models"
    try:
        r = requests.get(url, timeout=10)
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
        r = requests.post(url, json=payload, timeout=120)
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
        r = requests.post(url, json=payload, timeout=120)
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
        r = requests.post(url, json=payload, timeout=60)
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
        r = requests.post(url, json=payload, timeout=20)
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
        r = requests.post(url, files=files, timeout=30)
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
        r = requests.post(url, json=payload, headers=headers, timeout=15)
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
        r = requests.post(url, json=payload, timeout=120)
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
        r = requests.post(url, json=payload, timeout=120)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gateway Ollama chat failed: {e}")
    return JSONResponse(content={"status": r.status_code, "response": r.json()})
