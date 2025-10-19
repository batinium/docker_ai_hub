# ~/aihub/dashboard/app.py

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
import requests, os, time

# -- CONFIGURATION
BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

AIHUB_IP = os.environ.get("AIHUB_IP", "100.64.194.12")
LMSTUDIO_PORT = int(os.environ.get("LMSTUDIO_PORT", 1234))
KOKORO_PORT   = int(os.environ.get("KOKORO_PORT", 8880))
STT_REST_PORT = int(os.environ.get("STT_REST_PORT", 10400))
OPENWEBUI_PORT = int(os.environ.get("OPENWEBUI_PORT", 3000))
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", 8080))

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
        "upstream_endpoint": f"http://{AIHUB_IP}:{LMSTUDIO_PORT}/v1/chat/completions",
        "summary": "Send chat style prompts to LM Studio compatible models.",
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
            f"  http://{AIHUB_IP}:{LMSTUDIO_PORT}/v1/chat/completions \\",
            "  -H 'Content-Type: application/json' \\",
            "  -d '{\"model\":\"openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix@q5_1\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello, AI Hub!\"}],\"stream\":false}'"
        ]),
    },
    {
        "id": "lmstudio-models",
        "name": "List Models",
        "provider": "LM Studio",
        "category": "Language Models",
        "method": "POST",
        "local_endpoint": "/api/lmstudio/models",
        "upstream_endpoint": f"http://{AIHUB_IP}:{LMSTUDIO_PORT}/v1/models",
        "summary": "Enumerate all models exposed by LM Studio.",
        "inputs": [],
        "notes": [
            "Upstream request is a GET; the dashboard proxies via POST for convenience.",
            "Use returned IDs when calling chat or completion endpoints."
        ],
        "sample_payload": {
            "method": "GET",
            "url": f"http://{AIHUB_IP}:{LMSTUDIO_PORT}/v1/models"
        },
        "form_defaults": {},
        "curl_example": "\n".join([
            "curl -X GET \\",
            f"  http://{AIHUB_IP}:{LMSTUDIO_PORT}/v1/models"
        ]),
    },
    {
        "id": "kokoro-tts",
        "name": "Text to Speech",
        "provider": "Kokoro",
        "category": "Audio",
        "method": "POST",
        "local_endpoint": "/api/tts",
        "upstream_endpoint": f"http://{AIHUB_IP}:{KOKORO_PORT}/v1/audio/speech",
        "summary": "Turn text prompts into MP3 audio using Kokoro voices.",
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
            f"  http://{AIHUB_IP}:{KOKORO_PORT}/v1/audio/speech \\",
            "  -H 'Content-Type: application/json' \\",
            "  -d '{\"model\":\"kokoro\",\"input\":\"Hello from AI Hub!\",\"voice\":\"af_bella\",\"response_format\":\"mp3\",\"speed\":1.0}' \\",
            "  --output output.mp3"
        ]),
    },
    {
        "id": "openwebui-chat",
        "name": "Chat (Open WebUI)",
        "provider": "Open WebUI",
        "category": "Language Models",
        "method": "POST",
        "local_endpoint": "/api/openwebui/chat",
        "upstream_endpoint": f"http://{AIHUB_IP}:{OPENWEBUI_PORT}/api/chat/completions",
        "summary": "Send chat prompts to models orchestrated by Open WebUI using the OpenAI schema.",
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
            f"  http://{AIHUB_IP}:{OPENWEBUI_PORT}/api/chat/completions \\",
            "  -H 'Content-Type: application/json' \\",
            "  -d '{\"model\":\"qwen2.5:7b-instruct\",\"messages\":[{\"role\":\"user\",\"content\":\"Summarize the AI Hub services.\"}]}'"
        ]),
    },
    {
        "id": "gateway-lmstudio-chat",
        "name": "Gateway Chat Relay",
        "provider": "Nginx Gateway",
        "category": "Gateway",
        "method": "POST",
        "local_endpoint": "/api/gateway/chat",
        "upstream_endpoint": f"http://{AIHUB_IP}:{GATEWAY_PORT}/lmstudio/v1/chat/completions",
        "summary": "Test the shared nginx relay that exposes LM Studio over Tailscale.",
        "inputs": [
            {"field": "model", "type": "text", "description": "Model identifier handled by LM Studio."},
            {"field": "message", "type": "textarea", "description": "Prompt forwarded through the gateway."}
        ],
        "notes": [
            "Preferred entrypoint for remote clients; ensures traffic flows through the hardened gateway.",
            "Gateway also supports `/ollama/` and `/stt/` routes when those services are enabled."
        ],
        "sample_payload": {
            "model": "openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix@q5_1",
            "messages": [{"role": "user", "content": "Verify gateway routing."}],
            "stream": False
        },
        "form_defaults": {
            "model": "openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix@q5_1",
            "message": "Verify gateway routing."
        },
        "curl_example": "\n".join([
            "curl -X POST \\",
            f"  http://{AIHUB_IP}:{GATEWAY_PORT}/lmstudio/v1/chat/completions \\",
            "  -H 'Content-Type: application/json' \\",
            "  -d '{\"model\":\"openai-gpt-oss-20b-abliterated-uncensored-neo-imatrix@q5_1\",\"messages\":[{\"role\":\"user\",\"content\":\"Verify gateway routing.\"}],\"stream\":false}'"
        ]),
    },
    {
        "id": "faster-whisper-stt",
        "name": "Speech to Text",
        "provider": "Faster Whisper",
        "category": "Audio",
        "method": "POST",
        "local_endpoint": "/api/stt",
        "upstream_endpoint": f"http://{AIHUB_IP}:{STT_REST_PORT}/v1/audio/transcriptions",
        "summary": "Upload audio and receive a JSON transcription using Faster Whisper REST.",
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
            f"  http://{AIHUB_IP}:{STT_REST_PORT}/v1/audio/transcriptions \\",
            "  -H 'Accept: application/json' \\",
            "  -F 'file=@sample.wav'"
        ]),
    }
]

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
    )


@app.get("/api/services", response_class=JSONResponse)
async def list_services():
    """Expose service metadata for frontend or external tools."""
    return {
        "ip": AIHUB_IP,
        "ports": PORTS,
        "services": SERVICES,
    }

# -- API ROUTES for agent/service calls
@app.post("/api/chat")
async def chat(model: str = Form(...), message: str = Form(...)):
    """Send a chat request to LM Studio."""
    url = f"http://{AIHUB_IP}:{LMSTUDIO_PORT}/v1/chat/completions"
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
async def list_models():
    """List models currently hosted on LM Studio."""
    url = f"http://{AIHUB_IP}:{LMSTUDIO_PORT}/v1/models"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model listing failed: {e}")
    return JSONResponse(content={"status": r.status_code, "response": r.json()})

@app.post("/api/tts")
async def tts(text: str = Form(...), voice: str = Form("af_bella")):
    """Generate TTS via Kokoro, save locally and return playback path."""
    url = f"http://{AIHUB_IP}:{KOKORO_PORT}/v1/audio/speech"
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
async def stt(file: UploadFile = File(...)):
    """Upload a WAV/MP3 file and transcribe via Faster-Whisper REST."""
    url = f"http://{AIHUB_IP}:{STT_REST_PORT}/v1/audio/transcriptions"
    try:
        files = {"file": (file.filename, file.file, file.content_type)}
        r = requests.post(url, files=files, timeout=30)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT request failed: {e}")

    return JSONResponse(content={"status": r.status_code, "response": r.json()})


@app.post("/api/openwebui/chat")
async def openwebui_chat(model: str = Form(...), message: str = Form(...)):
    """Send a chat completion request through Open WebUI."""
    url = f"http://{AIHUB_IP}:{OPENWEBUI_PORT}/api/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
    }
    headers = {}
    api_key = os.environ.get("OPENWEBUI_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Open WebUI chat failed: {e}")
    return JSONResponse(content={"status": r.status_code, "response": r.json()})


@app.post("/api/gateway/chat")
async def gateway_chat(model: str = Form(...), message: str = Form(...)):
    """Relay chat completions through the nginx gateway."""
    url = f"http://{AIHUB_IP}:{GATEWAY_PORT}/lmstudio/v1/chat/completions"
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
