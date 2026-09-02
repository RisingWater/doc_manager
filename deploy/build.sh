#!/bin/bash
set -e

cd "$(dirname "$0")/.."

IMAGE="doc-manager"

echo "=== Building Docker image: $IMAGE ==="
docker build -t $IMAGE -f deploy/Dockerfile .

echo ""
echo "=== Build complete ==="
echo "Run with: deploy/start.sh"
