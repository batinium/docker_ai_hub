#!/usr/bin/env python3
"""
Example client for AI agents to interact with the AI Hub services.

The script shows how to:
  * List available LM Studio models
  * Send chat completions to LM Studio (direct or via the gateway)
  * Call the LM Studio responses, completions, and embeddings endpoints
  * Query Open WebUI (delegated to Ollama)
  * Generate speech with Kokoro
  * Transcribe audio with Faster Whisper

Usage:
  python ai_agent_example.py --help

Designed as reference code that LLM-based agents can study or reuse. When the
dashboard requires API keys, set `DASHBOARD_API_KEY`/`DASHBOARD_API_KEYS` or
pass `--dashboard-api-key` so the helper can authenticate with `X-API-Key`.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Dict, Iterable, List, Optional
import mimetypes

import requests


def _default_host() -> str:
    return os.environ.get("AIHUB_IP", os.environ.get("LAN_IP", "127.0.0.1"))


def _build_url(host: str, port: int, path: str) -> str:
    path = path[1:] if path.startswith("/") else path
    return f"http://{host}:{port}/{path}"


def _env_dashboard_api_key() -> Optional[str]:
    primary = os.environ.get("DASHBOARD_API_KEY")
    if primary and primary.strip():
        return primary.strip()
    keys = [key.strip() for key in os.environ.get("DASHBOARD_API_KEYS", "").split(",") if key.strip()]
    return keys[0] if keys else None


def _auth_headers(api_key: Optional[str] = None) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _json_headers(api_key: Optional[str] = None) -> Dict[str, str]:
    headers = _auth_headers(api_key)
    headers["Content-Type"] = "application/json"
    return headers


def _make_wav(text: str = "AI Hub sample audio", seconds: float = 1.0) -> io.BytesIO:
    """Create a temporary WAV file with silence to demonstrate STT uploads."""
    sample_rate = 16000
    total_frames = int(sample_rate * seconds)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * total_frames)
    buffer.seek(0)
    return buffer


SAMPLE_AUDIO_PATH = Path(__file__).with_name("test.mp3")
EXPECTED_SAMPLE_TRANSCRIPTION = "Hello from AI Hub, bridging models and utilities"


def _normalize_transcript(text: str) -> str:
    """Lowercase alphanumerics/space only for tolerant transcript comparison."""
    return "".join(ch.lower() for ch in text if ch.isalnum() or ch.isspace()).strip()


@dataclass
class HubConfig:
    host: str = _default_host()
    lmstudio_port: int = int(os.environ.get("LMSTUDIO_PORT", 1234))
    gateway_port: int = int(os.environ.get("GATEWAY_PORT", 8080))
    openwebui_port: int = int(os.environ.get("OPENWEBUI_PORT", 3000))
    kokoro_port: int = int(os.environ.get("KOKORO_PORT", 8880))
    stt_port: int = int(os.environ.get("STT_REST_PORT", 10400))
    lmstudio_model: str = os.environ.get("LMSTUDIO_MODEL", "qwen3-0.6b")
    lmstudio_completion_model: Optional[str] = os.environ.get("LMSTUDIO_COMPLETION_MODEL")
    lmstudio_embedding_model: Optional[str] = os.environ.get(
        "LMSTUDIO_EMBEDDING_MODEL", "text-embedding-qwen3-embedding-0.6b"
    )
    ollama_model: str = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
    kokoro_voice: str = os.environ.get("KOKORO_VOICE", "af_bella")
    openwebui_api_key: Optional[str] = os.environ.get("OPENWEBUI_API_KEY")
    dashboard_api_key: Optional[str] = _env_dashboard_api_key()
    timeout: int = int(os.environ.get("AGENT_TIMEOUT", 30))


class AIHubClient:
    """High-level helper for OpenAI-compatible services hosted on AI Hub."""

    def __init__(self, config: HubConfig):
        self.config = config
        self.session = requests.Session()

    # ----- Chat helpers -----------------------------------------------------
    def models_lmstudio(self) -> Dict:
        """List models exposed by the LM Studio OpenAI-compatible server."""
        url = _build_url(self.config.host, self.config.gateway_port, "/lmstudio/v1/models")
        resp = self.session.get(url, headers=_auth_headers(self.config.dashboard_api_key), timeout=self.config.timeout)
        resp.raise_for_status()
        return resp.json()

    def chat_lmstudio(self, messages: Iterable[Dict[str, str]]) -> Dict:
        url = _build_url(self.config.host, self.config.gateway_port, "/lmstudio/v1/chat/completions")
        payload = {"model": self.config.lmstudio_model, "messages": list(messages), "stream": False}
        resp = self.session.post(url, json=payload, headers=_json_headers(self.config.dashboard_api_key), timeout=self.config.timeout)
        resp.raise_for_status()
        return resp.json()

    def respond_lmstudio(self, prompt: str) -> Dict:
        """Call the LM Studio Responses endpoint."""
        url = _build_url(self.config.host, self.config.gateway_port, "/lmstudio/v1/responses")
        payload = {"model": self.config.lmstudio_model, "input": prompt}
        resp = self.session.post(url, json=payload, headers=_json_headers(self.config.dashboard_api_key), timeout=self.config.timeout)
        resp.raise_for_status()
        return resp.json()

    def complete_lmstudio(self, prompt: str) -> Dict:
        """Call the LM Studio Completions endpoint."""
        model = self.config.lmstudio_completion_model or self.config.lmstudio_model
        url = _build_url(self.config.host, self.config.gateway_port, "/lmstudio/v1/completions")
        payload = {"model": model, "prompt": prompt, "max_tokens": 120}
        resp = self.session.post(url, json=payload, headers=_json_headers(self.config.dashboard_api_key), timeout=self.config.timeout)
        resp.raise_for_status()
        return resp.json()

    def embed_lmstudio(self, text: str) -> Dict:
        """Call the LM Studio Embeddings endpoint."""
        model = self.config.lmstudio_embedding_model or self.config.lmstudio_model
        url = _build_url(self.config.host, self.config.gateway_port, "/lmstudio/v1/embeddings")
        payload = {"model": model, "input": text}
        resp = self.session.post(url, json=payload, headers=_json_headers(self.config.dashboard_api_key), timeout=self.config.timeout)
        resp.raise_for_status()
        return resp.json()

    def chat_openwebui(self, messages: Iterable[Dict[str, str]]) -> Dict:
        url = _build_url(self.config.host, self.config.gateway_port, "/openwebui/api/chat/completions")
        payload = {"model": self.config.ollama_model, "messages": list(messages)}
        headers = _json_headers(self.config.dashboard_api_key)
        if self.config.openwebui_api_key:
            headers["Authorization"] = f"Bearer {self.config.openwebui_api_key}"
        resp = self.session.post(url, json=payload, headers=headers, timeout=self.config.timeout)
        resp.raise_for_status()
        return resp.json()

    def chat_gateway(self, messages: Iterable[Dict[str, str]]) -> Dict:
        """Call LM Studio through the nginx gateway."""
        url = _build_url(self.config.host, self.config.gateway_port, "/lmstudio/v1/chat/completions")
        payload = {"model": self.config.lmstudio_model, "messages": list(messages), "stream": False}
        resp = self.session.post(url, json=payload, headers=_json_headers(self.config.dashboard_api_key), timeout=self.config.timeout)
        resp.raise_for_status()
        return resp.json()

    def chat_gateway_ollama(self, messages: Iterable[Dict[str, str]]) -> Dict:
        """Call Ollama through the nginx gateway."""
        url = _build_url(self.config.host, self.config.gateway_port, "/ollama/v1/chat/completions")
        payload = {"model": self.config.ollama_model, "messages": list(messages), "stream": False}
        resp = self.session.post(url, json=payload, headers=_json_headers(self.config.dashboard_api_key), timeout=self.config.timeout)
        resp.raise_for_status()
        return resp.json()

    # ----- Speech helpers ---------------------------------------------------
    def generate_speech(self, text: str, voice: Optional[str] = None, speed: float = 1.0) -> bytes:
        """Request Kokoro TTS and return the raw MP3 bytes."""
        url = _build_url(self.config.host, self.config.gateway_port, "/kokoro/v1/audio/speech")
        payload = {
            "model": "kokoro",
            "voice": voice or self.config.kokoro_voice,
            "input": text,
            "response_format": "mp3",
            "speed": speed,
        }
        resp = self.session.post(url, json=payload, headers=_json_headers(self.config.dashboard_api_key), timeout=self.config.timeout)
        resp.raise_for_status()
        return resp.content

    def transcribe_audio(
        self,
        wav_bytes: bytes,
        filename: str = "sample.wav",
        language: str = "en",
        model_override: Optional[str] = None,
    ) -> Dict:
        """Send audio bytes to Faster Whisper STT."""
        url = _build_url(self.config.host, self.config.gateway_port, "/stt/v1/audio/transcriptions")
        files = {"file": (filename, io.BytesIO(wav_bytes), "audio/wav")}
        data = {"language": language}
        if model_override:
            data["model_size"] = model_override
        resp = self.session.post(url, files=files, data=data, headers=_auth_headers(self.config.dashboard_api_key), timeout=self.config.timeout)
        resp.raise_for_status()
        return resp.json()

    def transcribe_file(
        self,
        path: Path,
        language: str = "en",
        model_override: Optional[str] = None,
    ) -> Dict:
        """Upload an audio file (e.g. MP3) to Faster Whisper STT."""
        url = _build_url(self.config.host, self.config.gateway_port, "/stt/v1/audio/transcriptions")
        mime_type, _ = mimetypes.guess_type(str(path))
        mime_type = mime_type or "application/octet-stream"
        data = {"language": language}
        if model_override:
            data["model_size"] = model_override
        with path.open("rb") as fh:
            files = {"file": (path.name, fh, mime_type)}
            resp = self.session.post(url, files=files, data=data, headers=_auth_headers(self.config.dashboard_api_key), timeout=self.config.timeout)
        resp.raise_for_status()
        return resp.json()


def run_demo(config: HubConfig) -> None:
    client = AIHubClient(config)
    prompt = [{"role": "user", "content": "Summarise the tools exposed by AI Hub."}]

    models = client.models_lmstudio()
    model_entries = models.get("data") or models.get("models") or []
    print("LM Studio models endpoint:")
    if isinstance(model_entries, list) and model_entries:
        print(json.dumps(model_entries[:5], indent=2))
    else:
        print(json.dumps(models, indent=2))
    print()

    print("LM Studio response (gateway /lmstudio):")
    lmstudio = client.chat_lmstudio(prompt)
    print(json.dumps(lmstudio, indent=2)[:600])
    print()

    try:
        webui = client.chat_openwebui(prompt)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        print(f"Open WebUI rejected the request (status {status}); ensure API key is set.")
    else:
        print("Open WebUI response (gateway /openwebui):")
        print(json.dumps(webui, indent=2)[:600])
    print()

    gateway = client.chat_gateway(prompt)
    print("Gateway alias → LM Studio response:")
    print(json.dumps(gateway, indent=2)[:600])
    print()

    try:
        gateway_ollama = client.chat_gateway_ollama(prompt)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        detail = exc.response.text[:200] if exc.response is not None else str(exc)
        print(f"Ollama gateway endpoint failed (status {status}): {detail}")
    else:
        print("Gateway → Ollama response:")
        print(json.dumps(gateway_ollama, indent=2)[:600])
    print()

    try:
        response = client.respond_lmstudio("Briefly describe the AI Hub architecture.")
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        detail = exc.response.text[:200] if exc.response is not None else str(exc)
        print(f"LM Studio responses endpoint failed (status {status}): {detail}")
    else:
        print("LM Studio responses endpoint:")
        print(json.dumps(response, indent=2)[:600])
    print()

    try:
        completion = client.complete_lmstudio("Write a short promotional slogan for AI Hub:\n")
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        detail = exc.response.text[:200] if exc.response is not None else str(exc)
        print(f"LM Studio completions endpoint failed (status {status}): {detail}")
    else:
        print("LM Studio completions endpoint:")
        print(json.dumps(completion, indent=2)[:600])
    print()

    try:
        embeddings = client.embed_lmstudio("Embedding probe for AI Hub services.")
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        detail = exc.response.text[:200] if exc.response is not None else str(exc)
        message = f"LM Studio embeddings endpoint failed (status {status}): {detail}"
        if status == 404 and "not embedding" in detail.lower():
            hint = (
                "Hint: set LMSTUDIO_EMBEDDING_MODEL to an embedding-capable model "
                "via env var or --lmstudio-embedding-model."
            )
            message = f"{message}\n{hint}"
        print(message)
    else:
        embedding_vec = embeddings.get("data", [{}])[0].get("embedding", [])
        preview = embedding_vec[:6] if isinstance(embedding_vec, list) else embedding_vec
        print("LM Studio embeddings endpoint:")
        print(json.dumps({"dimensions": len(embedding_vec), "preview": preview}, indent=2))
    print()

    audio_bytes = client.generate_speech(
        "AI Hub example voice check.",
        voice=config.kokoro_voice,
        speed=1.1,
    )
    print(f"Kokoro TTS returned {len(audio_bytes)} bytes of audio (voice={config.kokoro_voice}, speed=1.1).")

    silence = _make_wav().getvalue()
    stt = client.transcribe_audio(silence, language="en")
    print("Faster Whisper transcription response (silence probe):")
    print(json.dumps(stt, indent=2))

    if SAMPLE_AUDIO_PATH.exists():
        sample = client.transcribe_file(SAMPLE_AUDIO_PATH, language="en")
        transcript = sample.get("text", "").strip()
        matches = _normalize_transcript(transcript) == _normalize_transcript(EXPECTED_SAMPLE_TRANSCRIPTION)
        print("Faster Whisper transcription response (sample MP3):")
        print(json.dumps(sample, indent=2))
        print(f"Matches expected text? {'yes' if matches else 'no'}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reference AI Hub client script for agents.")
    parser.add_argument("--host", default=_default_host(), help="AI Hub host or IP.")
    parser.add_argument("--lmstudio-port", type=int, default=int(os.environ.get("LMSTUDIO_PORT", 1234)))
    parser.add_argument("--gateway-port", type=int, default=int(os.environ.get("GATEWAY_PORT", 8080)))
    parser.add_argument("--openwebui-port", type=int, default=int(os.environ.get("OPENWEBUI_PORT", 3000)))
    parser.add_argument("--kokoro-port", type=int, default=int(os.environ.get("KOKORO_PORT", 8880)))
    parser.add_argument("--stt-port", type=int, default=int(os.environ.get("STT_REST_PORT", 10400)))
    parser.add_argument("--lmstudio-model", default=os.environ.get("LMSTUDIO_MODEL", "qwen3-0.6b"))
    parser.add_argument("--lmstudio-completion-model", default=os.environ.get("LMSTUDIO_COMPLETION_MODEL"))
    parser.add_argument(
        "--lmstudio-embedding-model",
        default=os.environ.get("LMSTUDIO_EMBEDDING_MODEL", "text-embedding-qwen3-embedding-0.6b"),
    )
    parser.add_argument("--ollama-model", default=os.environ.get("OLLAMA_MODEL", "gemma3:4b"))
    parser.add_argument("--kokoro-voice", default=os.environ.get("KOKORO_VOICE", "af_bella"))
    parser.add_argument("--openwebui-api-key", default=os.environ.get("OPENWEBUI_API_KEY"))
    parser.add_argument(
        "--dashboard-api-key",
        default=os.environ.get("DASHBOARD_API_KEY"),
        help="API key for dashboard-secured endpoints (overrides DASHBOARD_API_KEY/DASHBOARD_API_KEYS).",
    )
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("AGENT_TIMEOUT", 30)))
    parser.add_argument("--no-demo", action="store_true", help="Importable mode; do not run the live demo.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    config = HubConfig(
        host=args.host,
        lmstudio_port=args.lmstudio_port,
        gateway_port=args.gateway_port,
        openwebui_port=args.openwebui_port,
        kokoro_port=args.kokoro_port,
        stt_port=args.stt_port,
        lmstudio_model=args.lmstudio_model,
        lmstudio_completion_model=args.lmstudio_completion_model,
        lmstudio_embedding_model=args.lmstudio_embedding_model,
        ollama_model=args.ollama_model,
        kokoro_voice=args.kokoro_voice,
        openwebui_api_key=args.openwebui_api_key,
        dashboard_api_key=args.dashboard_api_key or _env_dashboard_api_key(),
        timeout=args.timeout,
    )

    if args.no_demo:
        return 0

    try:
        run_demo(config)
    except requests.HTTPError as exc:
        response = exc.response
        status = response.status_code if response is not None else "?"
        detail = response.text[:500] if response is not None else str(exc)
        print(f"HTTPError: status={status} detail={detail}")
        return 1
    except requests.RequestException as exc:
        print(f"Request failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
