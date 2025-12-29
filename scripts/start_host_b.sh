#!/usr/bin/env bash
set -euo pipefail

# Arranca el host B: réplicas adicionales y frontend B.
# Variables:
#   COORD_IP    (obligatorio) IP del coordinador principal en host A.
#   NETWORK     (default agenda_net)
#   FRONT_PORT  (default 8502)

COORD_IP=${COORD_IP:-}
NETWORK=${NETWORK:-agenda_net}
FRONT_PORT=${FRONT_PORT:-8502}

# Parar y eliminar contenedores previos usados por este host
docker rm -f frontend_b \
  raft_events_nz_3 raft_events_nz_4 \
  raft_groups_2 raft_groups_3 \
  raft_users_2 raft_users_3 2>/dev/null || true

if [[ -z "$COORD_IP" ]]; then
  echo "❌ Debes exportar COORD_IP. Ej: COORD_IP=192.168.171.112" >&2
  exit 1
fi

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
  docker network create --driver overlay --attachable "$NETWORK" || docker network create "$NETWORK"
fi

SELF_IP=$(hostname -I | awk '{print $1}')
echo "➡️ Host B apuntando a coordinador en $COORD_IP | red $NETWORK | IP local $SELF_IP"

run_node() {
  local name=$1 port=$2 shard=$3 peers=$4
  docker run -d --name "$name" --hostname "$name" --network "$NETWORK" -p "${port}:${port}" \
    -v "${name}_data":/app/data \
    -e PYTHONPATH="/app:/app/backend" \
    -e SHARD_NAME="$shard" \
    -e NODE_ID="$name" \
    -e NODE_URL="http://${name}:${port}" \
    -e PORT="$port" \
    -e PEERS="$peers" \
    -e COORD_URL="http://coordinator:8700" \
    agenda_backend uvicorn distributed.nodes.raft_node:app --host 0.0.0.0 --port "$port"
}

echo "🚀 Lanzando nodos en Host B..."
run_node raft_events_nz_3 8806 EVENTOS_N_Z "http://raft_events_nz_1:8804,http://raft_events_nz_2:8805"
run_node raft_groups_2    8808 GRUPOS      "http://raft_groups_1:8807"
run_node raft_groups_3    8809 GRUPOS      "http://raft_groups_1:8807,http://raft_groups_2:8808"
run_node raft_users_2     8811 USUARIOS    "http://raft_users_1:8810"
run_node raft_users_3     8812 USUARIOS    "http://raft_users_1:8810,http://raft_users_2:8811"

# Nodo extra opcional en NZ para quorum amplio si no existe (descomentar si lo quieres en host B)
# run_node raft_events_nz_4 8814 EVENTOS_N_Z "http://raft_events_nz_1:8804,http://raft_events_nz_2:8805,http://raft_events_nz_3:8806"

echo "🎨 Lanzando frontend en Host B..."
docker rm -f frontend_b 2>/dev/null || true
docker run -d --name frontend_b --hostname frontend_b --network "$NETWORK" \
  -p ${FRONT_PORT}:8501 \
  -e PYTHONPATH="/app/front:/app" \
  -e API_BASE_URL=http://coordinator:8700 \
  -e WEBSOCKET_HOST=coordinator \
  -e WEBSOCKET_PORT=8767 \
  agenda_frontend streamlit run front/app.py --server.port=8501 --server.address=0.0.0.0

echo "✅ Host B listo. Front: http://${SELF_IP}:${FRONT_PORT}"
