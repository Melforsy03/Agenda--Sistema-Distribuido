#!/usr/bin/env bash
set -euo pipefail

# Levanta un balanceador Traefik que descubre coordinadores automáticamente por labels.
# Exponer puerto externo con LB_PORT (default 8702). Internamente usa 8700.
# Requiere acceso al socket Docker y que los coordinadores tengan labels traefik.enable=true.

NETWORK=${NETWORK:-agenda_net}
LB_PORT=${LB_PORT:-8702}

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
  docker network create --driver overlay --attachable "$NETWORK" || docker network create "$NETWORK"
fi

docker rm -f coordinator_lb 2>/dev/null || true

docker run -d --name coordinator_lb --network "$NETWORK" \
  -p ${LB_PORT}:8700 \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  traefik:v2.10 \
    --api.insecure=false \
    --providers.docker=true \
    --providers.docker.exposedbydefault=false \
    --providers.docker.network="${NETWORK}" \
    --entrypoints.web.address=":8700"

echo "✅ Balanceador listo en puerto ${LB_PORT}. Apunta los frontends a http://<host>:${LB_PORT}"
