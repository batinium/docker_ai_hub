#!/usr/bin/env python3
"""
Connectivity checks for AI Hub services using OpenAI-compatible endpoints.

Run this script on the server or a remote client to verify that the nginx
gateway is proxying each AI Hub service correctly. All probes target the
gateway routes (e.g. `/lmstudio/`, `/ollama/`, `/kokoro/`, `/stt/`). Set
connection details via environment variables or CLI flags as needed. When
`DASHBOARD_API_KEY`/`DASHBOARD_API_KEYS` is set, include an `X-API-Key` header
or pass `--dashboard-api-key`.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional

import requests

_SCRIPT_DIR = Path(__file__).resolve().parent
_DASHBOARD_DIR = _SCRIPT_DIR.parent
if str(_DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(_DASHBOARD_DIR))

from ip_utils import resolve_local_ip


def _load_env_defaults() -> None:
    """Populate os.environ from the repository-level .env if available."""
    root_dir = Path(__file__).resolve().parents[2]
    candidates = [root_dir / ".env"]
    for env_path in candidates:
        if not env_path.is_file():
            continue
        try:
            for raw_line in env_path.read_text().splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export ") :].strip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if not key or key in os.environ:
                    continue
                if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                os.environ[key] = value
        except OSError:
            continue


_load_env_defaults()


def _resolve_dashboard_key(explicit: Optional[str] = None) -> Optional[str]:
    if explicit and explicit.strip():
        return explicit.strip()
    primary = os.environ.get("DASHBOARD_API_KEY")
    if primary and primary.strip():
        return primary.strip()
    keys = [key.strip() for key in os.environ.get("DASHBOARD_API_KEYS", "").split(",") if key.strip()]
    return keys[0] if keys else None


def _headers(api_key: Optional[str], extra: Optional[dict] = None) -> dict:
    headers: dict = {}
    if api_key:
        headers["X-API-Key"] = api_key
    if extra:
        headers.update(extra)
    return headers


DEFAULT_TIMEOUT = 15


@dataclass
class TestContext:
    """Holds endpoint targets and request defaults."""

    ip: str
    gateway_port: int
    timeout: int
    lmstudio_model: Optional[str]
    openwebui_model: Optional[str]
    ollama_model: Optional[str]
    kokoro_voice: str
    openwebui_api_key: Optional[str]
    dashboard_api_key: Optional[str]


@dataclass
class TestResult:
    """Stores the outcome for a single connectivity test."""

    name: str
    ok: bool
    status_code: Optional[int]
    detail: str
    elapsed: float


TestFunc = Callable[[requests.Session, TestContext], TestResult]


def _json_chat_payload(model: str, message: str = "Hello from connectivity check!") -> dict:
    return {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "stream": False,
    }


def _generate_silence_wav(duration_seconds: float = 0.2, sample_rate: int = 16000) -> io.BytesIO:
    """Create an in-memory WAV file with silence."""
    frame_count = int(duration_seconds * sample_rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # 16-bit samples
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frame_count)
    buffer.seek(0)
    return buffer


def lmstudio_chat(session: requests.Session, ctx: TestContext) -> TestResult:
    if not ctx.lmstudio_model:
        return TestResult("Gateway → LM Studio chat", True, None, "Skipped (no LM Studio model provided)", 0.0)
    url = f"http://{ctx.ip}:{ctx.gateway_port}/lmstudio/v1/chat/completions"
    payload = _json_chat_payload(ctx.lmstudio_model)
    start = time.perf_counter()
    try:
        resp = session.post(url, json=payload, headers=_headers(ctx.dashboard_api_key), timeout=ctx.timeout)
        elapsed = time.perf_counter() - start
        resp.raise_for_status()
        data = resp.json()
        ok = bool(data.get("choices"))
        detail = "Received choices" if ok else "Empty response"
        return TestResult("Gateway → LM Studio chat", ok, resp.status_code, detail, elapsed)
    except Exception as exc:
        elapsed = time.perf_counter() - start
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return TestResult("Gateway → LM Studio chat", False, status, str(exc), elapsed)


def lmstudio_models(session: requests.Session, ctx: TestContext) -> TestResult:
    url = f"http://{ctx.ip}:{ctx.gateway_port}/lmstudio/v1/models"
    start = time.perf_counter()
    try:
        resp = session.get(url, headers=_headers(ctx.dashboard_api_key), timeout=ctx.timeout)
        elapsed = time.perf_counter() - start
        resp.raise_for_status()
        data = resp.json()
        models = data.get("data") or data.get("models") or []
        ok = isinstance(models, list) and len(models) > 0
        detail = f"{len(models)} models listed" if ok else "No models reported"
        return TestResult("Gateway → LM Studio models", ok, resp.status_code, detail, elapsed)
    except Exception as exc:
        elapsed = time.perf_counter() - start
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return TestResult("Gateway → LM Studio models", False, status, str(exc), elapsed)


def kokoro_tts(session: requests.Session, ctx: TestContext) -> TestResult:
    url = f"http://{ctx.ip}:{ctx.gateway_port}/kokoro/v1/audio/speech"
    payload = {
        "model": "kokoro",
        "input": "Testing Kokoro connectivity.",
        "voice": ctx.kokoro_voice,
        "response_format": "mp3",
        "speed": 1.0,
    }
    start = time.perf_counter()
    try:
        resp = session.post(url, json=payload, headers=_headers(ctx.dashboard_api_key), timeout=ctx.timeout)
        elapsed = time.perf_counter() - start
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        ok = "audio" in content_type
        detail = f"Content-Type: {content_type}"
        return TestResult("Gateway → Kokoro TTS", ok, resp.status_code, detail, elapsed)
    except Exception as exc:
        elapsed = time.perf_counter() - start
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return TestResult("Gateway → Kokoro TTS", False, status, str(exc), elapsed)


def faster_whisper_stt(session: requests.Session, ctx: TestContext) -> TestResult:
    url = f"http://{ctx.ip}:{ctx.gateway_port}/stt/v1/audio/transcriptions"
    wav_buffer = _generate_silence_wav()
    files = {
        "file": ("connectivity.wav", wav_buffer, "audio/wav"),
    }
    start = time.perf_counter()
    try:
        resp = session.post(url, files=files, headers=_headers(ctx.dashboard_api_key), timeout=ctx.timeout)
        elapsed = time.perf_counter() - start
        resp.raise_for_status()
        data = resp.json()
        text = data.get("text") or data.get("transcription") or ""
        detail = f"Transcription length: {len(text)}"
        return TestResult("Gateway → Faster Whisper STT", True, resp.status_code, detail, elapsed)
    except Exception as exc:
        elapsed = time.perf_counter() - start
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return TestResult("Gateway → Faster Whisper STT", False, status, str(exc), elapsed)


def openwebui_chat(session: requests.Session, ctx: TestContext) -> TestResult:
    if not ctx.openwebui_model:
        return TestResult("Gateway → Open WebUI chat", True, None, "Skipped (no Open WebUI model provided)", 0.0)
    url = f"http://{ctx.ip}:{ctx.gateway_port}/openwebui/api/chat/completions"
    payload = _json_chat_payload(ctx.openwebui_model, "Ping from connectivity check.")
    extra_headers = {}
    if ctx.openwebui_api_key:
        extra_headers["Authorization"] = f"Bearer {ctx.openwebui_api_key}"
    start = time.perf_counter()
    try:
        resp = session.post(url, json=payload, headers=_headers(ctx.dashboard_api_key, extra_headers), timeout=ctx.timeout)
        elapsed = time.perf_counter() - start
        resp.raise_for_status()
        data = resp.json()
        ok = bool(data.get("choices"))
        detail = "Received choices" if ok else "Empty response"
        return TestResult("Gateway → Open WebUI chat", ok, resp.status_code, detail, elapsed)
    except Exception as exc:
        elapsed = time.perf_counter() - start
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 401 and not ctx.openwebui_api_key:
            return TestResult(
                "Gateway → Open WebUI chat",
                True,
                status,
                "Reachable but API key required; skipping authenticated test",
                elapsed,
            )
        return TestResult("Gateway → Open WebUI chat", False, status, str(exc), elapsed)


def gateway_ollama_chat(session: requests.Session, ctx: TestContext) -> TestResult:
    if not ctx.ollama_model:
        return TestResult("Gateway → Ollama chat", True, None, "Skipped (no Ollama model provided)", 0.0)
    url = f"http://{ctx.ip}:{ctx.gateway_port}/ollama/v1/chat/completions"
    payload = _json_chat_payload(ctx.ollama_model, "Gateway Ollama connectivity probe.")
    start = time.perf_counter()
    try:
        resp = session.post(url, json=payload, headers=_headers(ctx.dashboard_api_key), timeout=ctx.timeout)
        elapsed = time.perf_counter() - start
        resp.raise_for_status()
        data = resp.json()
        ok = bool(data.get("choices"))
        detail = "Received choices" if ok else "Empty response"
        return TestResult("Gateway → Ollama chat", ok, resp.status_code, detail, elapsed)
    except Exception as exc:
        elapsed = time.perf_counter() - start
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return TestResult("Gateway → Ollama chat", False, status, str(exc), elapsed)


GATEWAY_TESTS: Iterable[TestFunc] = (
    lmstudio_models,
    lmstudio_chat,
    openwebui_chat,
    gateway_ollama_chat,
    kokoro_tts,
    faster_whisper_stt,
)

SERVER_TESTS: Iterable[TestFunc] = GATEWAY_TESTS
CLIENT_TESTS: Iterable[TestFunc] = GATEWAY_TESTS


def _parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["server", "client", "all"], default="all",
                        help="Choose which set of endpoints to verify.")
    env_ip = os.environ.get("AIHUB_IP") or os.environ.get("LAN_IP")
    env_ip = env_ip.strip() if env_ip else None
    parser.add_argument("--ip", default=env_ip or resolve_local_ip(),
                        help="AI Hub host/IP to target.")
    parser.add_argument("--gateway-port", type=int, default=int(os.environ.get("GATEWAY_PORT", 8080)))
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("CONNECTIVITY_TIMEOUT", DEFAULT_TIMEOUT)),
                        help="Per-request timeout in seconds.")
    parser.add_argument("--lmstudio-model", default=os.environ.get("LMSTUDIO_MODEL", "qwen3-06.b"),
                        help="Model ID to use for LM Studio chat tests.")
    parser.add_argument("--openwebui-model", default=os.environ.get("OPENWEBUI_MODEL"),
                        help="Model ID to use for Open WebUI chat tests.")
    parser.add_argument("--ollama-model", default=os.environ.get("OLLAMA_MODEL", "gemma3:4b"),
                        help="Model ID to use for Ollama chat tests.")
    parser.add_argument("--kokoro-voice", default=os.environ.get("KOKORO_VOICE", "af_bella"),
                        help="Voice preset to use for Kokoro speech tests.")
    parser.add_argument("--openwebui-api-key", default=os.environ.get("OPENWEBUI_API_KEY"),
                        help="API key for Open WebUI (if authentication is enabled).")
    parser.add_argument("--dashboard-api-key", default=os.environ.get("DASHBOARD_API_KEY"),
                        help="API key for the dashboard gateway (overrides DASHBOARD_API_KEY/DASHBOARD_API_KEYS).")
    return parser.parse_args(argv)


def _select_tests(mode: str) -> Iterable[TestFunc]:
    if mode in {"server", "client", "all"}:
        return GATEWAY_TESTS
    return GATEWAY_TESTS


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    if not args.openwebui_model:
        args.openwebui_model = args.ollama_model
    dashboard_api_key = _resolve_dashboard_key(args.dashboard_api_key)
    ctx = TestContext(
        ip=args.ip,
        gateway_port=args.gateway_port,
        timeout=args.timeout,
        lmstudio_model=args.lmstudio_model,
        openwebui_model=args.openwebui_model,
        ollama_model=args.ollama_model,
        kokoro_voice=args.kokoro_voice,
        openwebui_api_key=args.openwebui_api_key,
        dashboard_api_key=dashboard_api_key,
    )

    session = requests.Session()
    if ctx.dashboard_api_key:
        session.headers.update(_headers(ctx.dashboard_api_key))
    tests = _select_tests(args.mode)
    results: List[TestResult] = []
    for test in tests:
        result = test(session, ctx)
        results.append(result)

    ok = True
    print(f"{'Test':35} {'OK':>3} {'Status':>7} {'Elapsed (s)':>11} Detail")
    print("-" * 80)
    for result in results:
        ok = ok and result.ok
        status = result.status_code if result.status_code is not None else "-"
        indicator = "✔" if result.ok else "✘"
        print(f"{result.name:35} {indicator:>3} {status!s:>7} {result.elapsed:11.2f} {result.detail}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
