#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd -- "${script_dir}/.." && pwd)"
cd "${project_dir}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: Docker is not installed or is not available on PATH." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Error: Docker Compose v2 is not available." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example. Add OPENAI_API_KEY, then run this script again." >&2
  exit 1
fi

if ! grep -Eq '^OPENAI_API_KEY=.+$' .env; then
  echo "Error: OPENAI_API_KEY is empty in .env." >&2
  exit 1
fi

docker compose config --quiet
docker compose up --build -d "$@"

echo
docker compose ps
echo
echo "Stack started."
echo "Streamlit: http://localhost:8501"
echo "Grafana:   http://localhost:3000"
echo "Dashboard: http://localhost:3000/d/genai-eval-slice"
