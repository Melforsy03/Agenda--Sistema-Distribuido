#!/usr/bin/env bash
set -euo pipefail

# Despliega el mínimo viable del sistema distribuido en un manager:
# - 1 nodo por shard (sin tolerancia a fallos)
# - 1 coordinador apuntando solo a esos nodos
# - 1 frontend apuntando al coordinador
#
# Requisitos: imágenes agenda_backend y agenda_frontend construidas, Docker Swarm en modo manager.

NET=${NET:-agenda_net}
API_PORT=${API_PORT:-8766}
WS_PORT=${WS_PORT:-8767}
COORD_PORT=${COORD_PORT:-8700}
FRONT_PORT=${FRONT_PORT:-8501}
EXPOSE_HOST=${EXPOSE_HOST:-1}  # publica puertos de nodos en localhost
COORD_URL_DOCKER=${COORD_URL_DOCKER:-http://coordinator:80} # URL del coordinador vista desde los contenedores

echo "🌐 Creando red overlay $NET (si no existe)..."
docker network create --driver overlay --attachable "$NET" >/dev/null 2>&1 || true

echo "🚀 Lanzando nodos RAFT mínimos (sin peers, sin tolerancia)..."
EXP_ARGS=()
if [[ "$EXPOSE_HOST" == "1" ]]; then
  EXP_ARGS=(-p)
fi

docker run -d --name raft_users_1 --hostname raft_users_1 --network "$NET" \
  ${EXP_ARGS:+-p 8810:8810} \
  -e SHARD_NAME=USUARIOS -e NODE_ID=raft_users_1 -e NODE_URL=http://raft_users_1:8810 \
  -e PORT=8810 -e PEERS="" -e REPLICATION_FACTOR=1 -e COORD_URL="$COORD_URL_DOCKER" \
  agenda_backend uvicorn distributed.nodes.raft_node:app --host 0.0.0.0 --port 8810

docker run -d --name raft_groups_1 --hostname raft_groups_1 --network "$NET" \
  ${EXP_ARGS:+-p 8807:8807} \
  -e SHARD_NAME=GRUPOS -e NODE_ID=raft_groups_1 -e NODE_URL=http://raft_groups_1:8807 \
  -e PORT=8807 -e PEERS="" -e REPLICATION_FACTOR=1 -e COORD_URL="$COORD_URL_DOCKER" \
  agenda_backend uvicorn distributed.nodes.raft_node:app --host 0.0.0.0 --port 8807

docker run -d --name raft_events_am_1 --hostname raft_events_am_1 --network "$NET" \
  ${EXP_ARGS:+-p 8801:8801} \
  -e SHARD_NAME=EVENTOS_A_M -e NODE_ID=raft_events_am_1 -e NODE_URL=http://raft_events_am_1:8801 \
  -e PORT=8801 -e PEERS="" -e REPLICATION_FACTOR=1 -e COORD_URL="$COORD_URL_DOCKER" \
  agenda_backend uvicorn distributed.nodes.raft_node:app --host 0.0.0.0 --port 8801

docker run -d --name raft_events_nz_1 --hostname raft_events_nz_1 --network "$NET" \
  ${EXP_ARGS:+-p 8804:8804} \
  -e SHARD_NAME=EVENTOS_N_Z -e NODE_ID=raft_events_nz_1 -e NODE_URL=http://raft_events_nz_1:8804 \
  -e PORT=8804 -e PEERS="" -e REPLICATION_FACTOR=1 -e COORD_URL="$COORD_URL_DOCKER" \
  agenda_backend uvicorn distributed.nodes.raft_node:app --host 0.0.0.0 --port 8804

echo "🧭 Lanzando coordinador..."
export SHARDS_CONFIG_JSON=${SHARDS_CONFIG_JSON:-'{
  "eventos_a_m":["http://raft_events_am_1:8801"],
  "eventos_n_z":["http://raft_events_nz_1:8804"],
  "groups":["http://raft_groups_1:8807"],
  "users":["http://raft_users_1:8810"]
}'}

docker run -d --name coordinator --hostname coordinator --network "$NET" \
  -p ${COORD_PORT}:80 \
  -e SHARDS_CONFIG_JSON="$SHARDS_CONFIG_JSON" \
  agenda_backend uvicorn distributed.coordinator.router:app --host 0.0.0.0 --port 80

echo "🎨 Lanzando frontend..."
docker run -d --name frontend --hostname frontend --network "$NET" \
  -p ${FRONT_PORT}:${FRONT_PORT} \
  -e API_BASE_URL=http://coordinator:80 \
  -e WEBSOCKET_HOST=coordinator -e WEBSOCKET_PORT=${WS_PORT} \
  agenda_frontend streamlit run front/app.py --server.port=${FRONT_PORT} --server.address=0.0.0.0

echo "✅ Despliegue mínimo listo."
echo "  - Coordinador: http://localhost:${COORD_PORT}"
echo "  - Frontend:    http://localhost:${FRONT_PORT}"
echo "  - WebSocket:   ws://localhost:${WS_PORT}"
