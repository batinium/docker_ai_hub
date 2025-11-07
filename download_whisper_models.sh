#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="faster-whisper"
# Determine the project directory dynamically
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_VOLUME_PATH="${SCRIPT_DIR}/faster-whisper-data"   # relative to project root
LANG="en"

# Broad list of model sizes (use valid names from docs)
MODELS=(
  "tiny.en" "tiny" 
  "base.en" "base" 
  "small.en" "small" 
  "medium.en" "medium" 
  "large-v1" "large-v2" "large-v3" "large"
  "distil-large-v2" "distil-medium.en" "distil-small.en"
  "distil-large-v3" "distil-large-v3.5" "large-v3-turbo" "turbo"
)

echo "==> Ensure container '${CONTAINER_NAME}' is running..."
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "ERROR: container '${CONTAINER_NAME}' is not running. Start it first." >&2
  exit 1
fi

echo "==> Downloading many models for faster-whisper..."
for MODEL in "${MODELS[@]}"; do
  echo "--> Model: ${MODEL}"
  docker exec -u 0 "${CONTAINER_NAME}" bash -c "\
    pip install faster-whisper soundfile numpy >/dev/null 2>&1 && \
    python3 - << 'PYCODE'
from faster_whisper import WhisperModel
print('Downloading model: ${MODEL}')
model = WhisperModel('${MODEL}', device='cpu', compute_type='int8')
# Optional: one dummy transcribe to trigger download
# We'll skip heavy transcribe for big models to save time/resources
# but load the model to force download
_ = model
print('Model ${MODEL} loaded.')
PYCODE
  "
  echo "   Model ${MODEL} done."
done

echo "==> Finished. Models downloaded under '${CONFIG_VOLUME_PATH}'."