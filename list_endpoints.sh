#!/usr/bin/env bash
set -euo pipefail

# Configure your endpoints (relative paths) and base URL
BASE_URL="http://0.0.0.0"            # local binding, or your host IP
PORTS=( 1234 11434 10300 8880 )
ROUTES=( \
  "/v1/models" \
  "/api/generate" \
  "/v1/audio/transcriptions" \
  "/v1/audio/speech" \
)

LOGFILE="./endpoint_list_$(date +%F_%T).log"

echo "Listing endpoints (base ${BASE_URL})" | tee "$LOGFILE"
for i in "${!PORTS[@]}"; do
  port="${PORTS[$i]}"
  route="${ROUTES[$i]}"
  url="${BASE_URL}:${port}${route}"
  echo "Checking URL: $url" | tee -a "$LOGFILE"
  # Using curl HEAD to test
  if curl --silent --head --fail "$url" >/dev/null; then
    echo "  ✅ Reachable" | tee -a "$LOGFILE"
  else
    echo "  ❌ Not reachable" | tee -a "$LOGFILE"
  fi
done

echo "Done. Log saved to $LOGFILE"