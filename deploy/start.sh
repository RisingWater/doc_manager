#!/bin/bash
set -e

cd "$(dirname "$0")/.."

IMAGE="doc-manager"
NAME="doc-manager"
HOST_PORT="${HOST_PORT:-8000}"

if [ "$(docker ps -aq -f name=^${NAME}$)" != "" ]; then
    echo "=== Container '$NAME' exists, starting it ==="
    docker start $NAME
    docker ps -f name=^${NAME}$
    echo "=== Server: http://127.0.0.1:${HOST_PORT} ==="
    exit 0
fi

echo "=== Starting container '$NAME' ==="
echo "=== Note: 容器以 UID ${UID:-1002} 运行，请确保当前目录及 data/ uploads/ 对该 UID 可写 ==="
docker run -d \
    --name $NAME \
    --restart unless-stopped \
    -p ${HOST_PORT}:8000 \
    -e SCAN_INTERVAL_MINUTES="${SCAN_INTERVAL_MINUTES:-30}" \
    -v "$(pwd)":/workdir \
    $IMAGE

docker ps -f name=^${NAME}$
echo "=== Server: http://127.0.0.1:${HOST_PORT} ==="
echo "=== Logs: docker logs -f $NAME ==="
