# AI Hub Agent Guide (Gateway Only)

This setup runs a lightweight nginx gateway with local model services. No dashboard or UI is included.

## Base URLs

- Gateway (Tailscale): `http://100.120.207.64:8080`
- Gateway (LAN): `http://192.168.1.103:8080` (if routed on your LAN)

## Authentication (Optional)

If `GATEWAY_API_KEYS` is set in `.env`, include `X-API-Key` with every request.

## LM Studio (OpenAI-compatible)

- Models: `GET /lmstudio/v1/models`
- Responses: `POST /lmstudio/v1/responses`
- Chat: `POST /lmstudio/v1/chat/completions`
- Completions: `POST /lmstudio/v1/completions`
- Embeddings: `POST /lmstudio/v1/embeddings`

Example:
```bash
curl http://100.120.207.64:8080/lmstudio/v1/responses \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"model":"google/gemma-3-4b","input":"Hello"}'
```

## Kokoro TTS

- Speech: `POST /kokoro/v1/audio/speech`

Example:
```bash
curl http://100.120.207.64:8080/kokoro/v1/audio/speech \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"model":"kokoro","input":"Hello","voice":"af_bella","response_format":"mp3"}' \
  --output hello.mp3
```

## Faster Whisper STT

- Transcriptions: `POST /stt/v1/audio/transcriptions`

Example:
```bash
curl http://100.120.207.64:8080/stt/v1/audio/transcriptions \
  -H "X-API-Key: <your-key>" \
  -F "file=@sample.wav"
```

## OpenRouter (optional)

The gateway proxy for OpenRouter is enabled in `proxy/nginx.conf.template`. Set `OPENROUTER_API_KEY` in `.env` to activate it.

Gateway example:
```bash
curl http://100.120.207.64:8080/openrouter/v1/chat/completions \
  -H "X-API-Key: <your-key>" \
  -H "Content-Type: application/json" \
  -d '{"model":"openrouter/auto","messages":[{"role":"user","content":"Hello"}]}'
```
