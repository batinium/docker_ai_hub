#!/usr/bin/env python3
"""
Example client for AI agents to interact with the AI Hub services.

The script shows how to:
  * Send chat completions to LM Studio (direct or via the gateway)
  * Query Open WebUI (delegated to Ollama)
  * Generate speech with Kokoro
  * Transcribe audio with Faster Whisper

Usage:
  python ai_agent_example.py --help

Designed as reference code that LLM-based agents can study or reuse.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import wave
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import requests


def _default_host() -> str:
    return os.environ.get("AIHUB_IP", "127.0.0.1")


def _build_url(host: str, port: int, path: str) -> str:
    path = path[1:] if path.startswith("/") else path
    return f"http://{host}:{port}/{path}"


def _headers(api_key: Optional[str] = None) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
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


@dataclass
class HubConfig:
    host: str = _default_host()
    lmstudio_port: int = int(os.environ.get("LMSTUDIO_PORT", 1234))
    gateway_port: int = int(os.environ.get("GATEWAY_PORT", 8080))
    openwebui_port: int = int(os.environ.get("OPENWEBUI_PORT", 3000))
    kokoro_port: int = int(os.environ.get("KOKORO_PORT", 8880))
    stt_port: int = int(os.environ.get("STT_REST_PORT", 10400))
    lmstudio_model: str = os.environ.get("LMSTUDIO_MODEL", "qwen3-0.6b")
    ollama_model: str = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
    kokoro_voice: str = os.environ.get("KOKORO_VOICE", "af_bella")
    openwebui_api_key: Optional[str] = os.environ.get("OPENWEBUI_API_KEY")
    timeout: int = int(os.environ.get("AGENT_TIMEOUT", 30))


class AIHubClient:
    """High-level helper for OpenAI-compatible services hosted on AI Hub."""

    def __init__(self, config: HubConfig):
        self.config = config
        self.session = requests.Session()

    # ----- Chat helpers -----------------------------------------------------
    def chat_lmstudio(self, messages: Iterable[Dict[str, str]]) -> Dict:
        url = _build_url(self.config.host, self.config.lmstudio_port, "/v1/chat/completions")
        payload = {"model": self.config.lmstudio_model, "messages": list(messages), "stream": False}
        resp = self.session.post(url, json=payload, headers=_headers(), timeout=self.config.timeout)
        resp.raise_for_status()
        return resp.json()

    def chat_openwebui(self, messages: Iterable[Dict[str, str]]) -> Dict:
        url = _build_url(self.config.host, self.config.openwebui_port, "/api/chat/completions")
        payload = {"model": self.config.ollama_model, "messages": list(messages)}
        resp = self.session.post(
            url,
            json=payload,
            headers=_headers(self.config.openwebui_api_key),
            timeout=self.config.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def chat_gateway(self, messages: Iterable[Dict[str, str]]) -> Dict:
        """Call LM Studio through the nginx gateway."""
        url = _build_url(self.config.host, self.config.gateway_port, "/lmstudio/v1/chat/completions")
        payload = {"model": self.config.lmstudio_model, "messages": list(messages), "stream": False}
        resp = self.session.post(url, json=payload, headers=_headers(), timeout=self.config.timeout)
        resp.raise_for_status()
        return resp.json()

    # ----- Speech helpers ---------------------------------------------------
    def generate_speech(self, text: str) -> bytes:
        """Request Kokoro TTS and return the raw MP3 bytes."""
        url = _build_url(self.config.host, self.config.kokoro_port, "/v1/audio/speech")
        payload = {
            "model": "kokoro",
            "voice": self.config.kokoro_voice,
            "input": text,
            "response_format": "mp3",
        }
        resp = self.session.post(url, json=payload, timeout=self.config.timeout)
        resp.raise_for_status()
        return resp.content

    def transcribe_audio(self, wav_bytes: bytes) -> Dict:
        """Send audio bytes to Faster Whisper STT."""
        url = _build_url(self.config.host, self.config.stt_port, "/v1/audio/transcriptions")
        files = {"file": ("sample.wav", io.BytesIO(wav_bytes), "audio/wav")}
        resp = self.session.post(url, files=files, timeout=self.config.timeout)
        resp.raise_for_status()
        return resp.json()


def run_demo(config: HubConfig) -> None:
    client = AIHubClient(config)
    prompt = [{"role": "user", "content": "Summarise the tools exposed by AI Hub."}]

    print("LM Studio response:")
    lmstudio = client.chat_lmstudio(prompt)
    print(json.dumps(lmstudio, indent=2)[:600])
    print()

    try:
        webui = client.chat_openwebui(prompt)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        print(f"Open WebUI rejected the request (status {status}); ensure API key is set.")
    else:
        print("Open WebUI response (via Ollama):")
        print(json.dumps(webui, indent=2)[:600])
    print()

    gateway = client.chat_gateway(prompt)
    print("Gateway → LM Studio response:")
    print(json.dumps(gateway, indent=2)[:600])
    print()

    audio_bytes = client.generate_speech("AI Hub example voice check.")
    print(f"Kokoro TTS returned {len(audio_bytes)} bytes of audio.")

    silence = _make_wav().getvalue()
    stt = client.transcribe_audio(silence)
    print("Faster Whisper transcription response:")
    print(json.dumps(stt, indent=2))


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reference AI Hub client script for agents.")
    parser.add_argument("--host", default=_default_host(), help="AI Hub host or IP.")
    parser.add_argument("--lmstudio-port", type=int, default=int(os.environ.get("LMSTUDIO_PORT", 1234)))
    parser.add_argument("--gateway-port", type=int, default=int(os.environ.get("GATEWAY_PORT", 8080)))
    parser.add_argument("--openwebui-port", type=int, default=int(os.environ.get("OPENWEBUI_PORT", 3000)))
    parser.add_argument("--kokoro-port", type=int, default=int(os.environ.get("KOKORO_PORT", 8880)))
    parser.add_argument("--stt-port", type=int, default=int(os.environ.get("STT_REST_PORT", 10400)))
    parser.add_argument("--lmstudio-model", default=os.environ.get("LMSTUDIO_MODEL", "qwen3-0.6b"))
    parser.add_argument("--ollama-model", default=os.environ.get("OLLAMA_MODEL", "gemma3:4b"))
    parser.add_argument("--kokoro-voice", default=os.environ.get("KOKORO_VOICE", "af_bella"))
    parser.add_argument("--openwebui-api-key", default=os.environ.get("OPENWEBUI_API_KEY"))
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
        ollama_model=args.ollama_model,
        kokoro_voice=args.kokoro_voice,
        openwebui_api_key=args.openwebui_api_key,
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
