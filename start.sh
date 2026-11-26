#!/bin/sh
set -eu

cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "Docker is installed but not running. Start Docker Desktop first."
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose is unavailable. Install the Docker Compose plugin."
    exit 1
fi

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example."
    echo "For live mode, add your API keys. For offline demo mode, set APP_PROVIDER_MODE=demo."
fi

docker compose up --build -d
docker compose ps
