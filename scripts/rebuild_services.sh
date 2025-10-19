#!/usr/bin/env bash
#
# Helper to rebuild and restart selected Docker Compose services.
# Usage:
#   ./scripts/rebuild_services.sh                # interactive selection
#   ./scripts/rebuild_services.sh svc1 svc2 ...  # non-interactive

set -euo pipefail

error() {
  echo "Error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || error "'$1' command not found. Please install it first."
}

require_cmd docker
if ! docker compose version >/dev/null 2>&1; then
  error "'docker compose' CLI plugin not available. Install Docker Desktop or the standalone Compose V2 binary."
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

ALL_SERVICES=()
while IFS= read -r svc; do
  [[ -z "${svc}" ]] && continue
  ALL_SERVICES+=("${svc}")
done < <(docker compose config --services 2>/dev/null)

if [[ ${#ALL_SERVICES[@]} -eq 0 ]]; then
  error "No services discovered via 'docker compose config --services'."
fi

declare -a SELECTED_SERVICES=()

dedupe_append() {
  local item
  local idx
  for ((idx = 0; idx < ${#SELECTED_SERVICES[@]}; idx++)); do
    item="${SELECTED_SERVICES[idx]}"
    [[ "${item}" == "$1" ]] && return
  done
  SELECTED_SERVICES+=("$1")
}

parse_indices() {
  local input="$1"
  local raw entries idx
  IFS=',' read -r -a entries <<<"${input}"
  for raw in "${entries[@]}"; do
    local trimmed="${raw//[[:space:]]/}"
    [[ -z "${trimmed}" ]] && continue
    local lowered
    lowered="$(printf '%s' "${trimmed}" | tr '[:upper:]' '[:lower:]')"
    if [[ "${lowered}" == "a" || "${lowered}" == "all" ]]; then
      SELECTED_SERVICES=("${ALL_SERVICES[@]}")
      return
    fi
    if ! [[ "${trimmed}" =~ ^[0-9]+$ ]]; then
      error "Invalid selection '${trimmed}'. Use numbers, 'a', or 'all'."
    fi
    idx=$((trimmed - 1))
    if (( idx < 0 || idx >= ${#ALL_SERVICES[@]} )); then
      error "Selection '${trimmed}' is out of range."
    fi
    dedupe_append "${ALL_SERVICES[idx]}"
  done
}

if (( $# > 0 )); then
  for svc in "$@"; do
    found=false
    for existing in "${ALL_SERVICES[@]}"; do
      if [[ "${existing}" == "${svc}" ]]; then
        dedupe_append "${svc}"
        found=true
        break
      fi
    done
    if ! ${found}; then
      error "Unknown service '${svc}'. Valid options: ${ALL_SERVICES[*]}"
    fi
  done
else
  echo "Available services:"
  for idx in "${!ALL_SERVICES[@]}"; do
    printf " %2d) %s\n" $((idx + 1)) "${ALL_SERVICES[idx]}"
  done
  echo "Choose services to rebuild (comma-separated numbers, 'a' for all)."
  read -r -p "Selection [a]: " selection
  if [[ -z "${selection//[[:space:]]/}" ]]; then
    SELECTED_SERVICES=("${ALL_SERVICES[@]}")
  else
    parse_indices "${selection}"
    if [[ ${#SELECTED_SERVICES[@]} -eq 0 ]]; then
      SELECTED_SERVICES=("${ALL_SERVICES[@]}")
    fi
  fi
fi

if [[ ${#SELECTED_SERVICES[@]} -eq 0 ]]; then
  error "No services selected."
fi

echo "Services selected: ${SELECTED_SERVICES[*]}"
echo ">>> docker compose build ${SELECTED_SERVICES[*]}"
docker compose build "${SELECTED_SERVICES[@]}"

echo ">>> docker compose up -d ${SELECTED_SERVICES[*]}"
docker compose up -d "${SELECTED_SERVICES[@]}"

echo "Done."
