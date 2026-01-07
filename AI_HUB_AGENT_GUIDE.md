# AI Hub Service Guide (Agentic Clients)

Use this file when integrating external apps or agents with the AI Hub gateway.

## Base URLs

- Tailscale: `http://100.120.207.64:8080`
- LAN: `http://192.168.1.103:8080`

## Auth

If `GATEWAY_API_KEYS` is set in `.env`, add `X-API-Key: <your-key>` to every request.

## LLM (LM Studio, OpenAI-compatible)

- Models: `GET /lmstudio/v1/models`
- Chat: `POST /lmstudio/v1/chat/completions`
- Responses: `POST /lmstudio/v1/responses`
- Completions: `POST /lmstudio/v1/completions`
- Embeddings: `POST /lmstudio/v1/embeddings`

Example:
```bash
curl http://100.120.207.64:8080/lmstudio/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"model":"google/gemma-3-4b","messages":[{"role":"user","content":"Hello"}]}'
```

## TTS (Kokoro)

- Speech: `POST /kokoro/v1/audio/speech`

Example:
```bash
curl http://100.120.207.64:8080/kokoro/v1/audio/speech \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"model":"kokoro","input":"Hello","voice":"af_bella","response_format":"mp3"}' \
  --output hello.mp3
```

## STT (Faster Whisper)

- Transcriptions: `POST /stt/v1/audio/transcriptions`

Example:
```bash
curl http://100.120.207.64:8080/stt/v1/audio/transcriptions \
  -H "X-API-Key: <your-key>" \
  -F "file=@sample.wav"
```

## OpenRouter (Optional)

Set `OPENROUTER_API_KEY` in `.env` to enable.

- Chat: `POST /openrouter/v1/chat/completions`

Example:
```bash
curl http://100.120.207.64:8080/openrouter/v1/chat/completions \
  -H "X-API-Key: <your-key>" \
  -H "Content-Type: application/json" \
  -d '{"model":"openrouter/auto","messages":[{"role":"user","content":"Hello"}]}'
```
