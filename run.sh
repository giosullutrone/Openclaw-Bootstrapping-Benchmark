#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# OpenClaw Bootstrapping Benchmark – one-command launcher
# ──────────────────────────────────────────────────────────────
#
# This script:
#   1. Creates a Python virtual-env (.venv) if it doesn't exist.
#   2. Installs / upgrades all required packages.
#   3. Runs the benchmark, forwarding every CLI flag you pass.
#
# Usage:
#   ./run.sh                        # run with defaults
#   ./run.sh --verbose              # debug logging
#   ./run.sh --models qwen3-vl-30b  # single model
#   ./run.sh --runs 3 --keep-env    # 3 runs, keep temp dirs
#   ./run.sh --preflight-only       # just check prerequisites
#
# All flags after ./run.sh are passed straight through to
# run_benchmark.py.  Run  ./run.sh --help  to see them all.
# ──────────────────────────────────────────────────────────────
set -euo pipefail

# ── Resolve project root (where this script lives) ──────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
REQUIREMENTS="requirements.txt"
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=10

# ── Colours (disabled when stdout is not a terminal) ─────────
if [[ -t 1 ]]; then
  BOLD="\033[1m"
  GREEN="\033[32m"
  YELLOW="\033[33m"
  RED="\033[31m"
  RESET="\033[0m"
else
  BOLD="" GREEN="" YELLOW="" RED="" RESET=""
fi

info()  { printf "${BOLD}${GREEN}▸${RESET} %s\n" "$*"; }
warn()  { printf "${BOLD}${YELLOW}▸${RESET} %s\n" "$*"; }
error() { printf "${BOLD}${RED}✖${RESET} %s\n" "$*" >&2; }

# ── Find a usable Python ≥ 3.10 ─────────────────────────────
find_python() {
  local candidates=("python3" "python")
  for cmd in "${candidates[@]}"; do
    if command -v "$cmd" &>/dev/null; then
      local ver
      ver="$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)" || continue
      local major minor
      major="${ver%%.*}"
      minor="${ver#*.}"
      if (( major > PYTHON_MIN_MAJOR || (major == PYTHON_MIN_MAJOR && minor >= PYTHON_MIN_MINOR) )); then
        echo "$cmd"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON="$(find_python)" || {
  error "Python ≥ ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR} is required but was not found on PATH."
  error "Install it from https://www.python.org/downloads/ and try again."
  exit 1
}
info "Using $(command -v "$PYTHON") ($("$PYTHON" --version 2>&1))"

# ── Create the virtual-env if it doesn't exist ──────────────
if [[ ! -d "$VENV_DIR" ]]; then
  info "Creating virtual environment in ${VENV_DIR}/ …"
  "$PYTHON" -m venv "$VENV_DIR"
else
  info "Virtual environment ${VENV_DIR}/ already exists — reusing."
fi

# ── Activate the venv ────────────────────────────────────────
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

# ── Install / upgrade dependencies ───────────────────────────
if [[ ! -f "$REQUIREMENTS" ]]; then
  error "requirements.txt not found in ${SCRIPT_DIR}."
  exit 1
fi

info "Installing dependencies from ${REQUIREMENTS} …"
pip install --quiet --upgrade pip
pip install --quiet --upgrade -r "$REQUIREMENTS"

# ── Run the benchmark ────────────────────────────────────────
info "Launching benchmark …"
echo ""
python run_benchmark.py "$@"
