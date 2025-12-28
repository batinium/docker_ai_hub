#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PATH="${REPO_ROOT}/.venv"

PYTHON_BIN="${PYTHON_BIN:-python3}"
PIP_BIN=""

if [[ ! -d "${VENV_PATH}" ]]; then
  echo "Creating virtual environment at ${VENV_PATH}"
  "${PYTHON_BIN}" -m venv "${VENV_PATH}"
else
  echo "Reusing existing virtual environment at ${VENV_PATH}"
fi

if [[ -f "${VENV_PATH}/bin/activate" ]]; then
  # shellcheck disable=SC1090
  source "${VENV_PATH}/bin/activate"
  PIP_BIN="pip"
elif [[ -f "${VENV_PATH}/Scripts/activate" ]]; then
  # Windows (WSL/PowerShell)
  # shellcheck disable=SC1091
  source "${VENV_PATH}/Scripts/activate"
  PIP_BIN="pip"
else
  echo "Unable to locate virtualenv activation script" >&2
  exit 1
fi

echo "Upgrading pip..."
"${PIP_BIN}" install --upgrade pip

echo "Installing dashboard/server dependencies..."
"${PIP_BIN}" install -r "${REPO_ROOT}/requirements/server.txt"

echo ""
echo "Server environment ready."
echo "Next steps:"
echo "  1. source ${VENV_PATH}/bin/activate"
echo "  2. cd dashboard"
echo "  3. uvicorn app:app --host 0.0.0.0 --port 8090"
