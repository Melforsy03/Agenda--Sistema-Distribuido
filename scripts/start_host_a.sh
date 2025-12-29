#!/usr/bin/env bash
set -euo pipefail

# Arranca el host A: coordinador principal + frontend + nodos base.
# Requiere que HOST_B_IP apunte al otro host.
#
# Opcionales:
#   NETWORK     (default agenda_net)
#   FRONT_PORT  (default 8501)
#   WS_PORT     (default 8768, mapea al 8767 interno del coordinador)

HOST_B_IP=${HOST_B_IP:-}
NETWORK=${NETWORK:-agenda_net}
FRONT_PORT=${FRONT_PORT:-8501}
WS_PORT=${WS_PORT:-8768}

if [[ -z "$HOST_B_IP" ]]; then
  echo "❌ Debes exportar HOST_B_IP. Ej: HOST_B_IP=192.168.171.147" >&2
  exit 1
fi

echo "➡️ Host A usando HOST_B_IP=$HOST_B_IP"

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
  docker network create --driver overlay --attachable "$NETWORK" || docker network create "$NETWORK"
fi

SELF_IP=$(hostname -I | awk '{print $1}')

# URLs por shard (nombres de contenedor + puertos internos)
EVENTS_AM=("http://raft_events_am_1:8801" "http://raft_events_am_2:8802")
EVENTS_NZ=("http://raft_events_nz_1:8804" "http://raft_events_nz_2:8805" "http://raft_events_nz_3:8806")
GROUPS=("http://raft_groups_1:8807" "http://raft_groups_2:8808" "http://raft_groups_3:8809")
USERS=("http://raft_users_1:8810" "http://raft_users_2:8811" "http://raft_users_3:8812")

echo "🌐 Red: $NETWORK | IP local: $SELF_IP | Host B: $HOST_B_IP"

run_node() {
  local name=$1 port=$2 shard=$3 peers=$4 coord_url=$5 volume=$6
  docker run -d --name "$name" --hostname "$name" --network "$NETWORK" -p "${port}:${port}" \
    -v "$volume":/app/data \
    -e PYTHONPATH="/app:/app/backend" \
    -e SHARD_NAME="$shard" \
    -e NODE_ID="$name" \
    -e NODE_URL="http://${name}:${port}" \
    -e PORT="$port" \
    -e PEERS="$peers" \
    -e COORD_URL="$coord_url" \
    agenda_backend uvicorn distributed.nodes.raft_node:app --host 0.0.0.0 --port "$port"
}

echo "🚀 Lanzando nodos en Host A..."
run_node raft_events_am_1 8801 EVENTOS_A_M "http://raft_events_am_2:8802" "http://coordinator:8700" raft_data_am1
run_node raft_events_am_2 8802 EVENTOS_A_M "http://raft_events_am_1:8801" "http://coordinator:8700" raft_data_am2
run_node raft_events_nz_1 8804 EVENTOS_N_Z "http://raft_events_nz_2:8805,http://raft_events_nz_3:8806" "http://coordinator:8700" raft_data_nz1
run_node raft_events_nz_2 8805 EVENTOS_N_Z "http://raft_events_nz_1:8804,http://raft_events_nz_3:8806" "http://coordinator:8700" raft_data_nz2
run_node raft_groups_1    8807 GRUPOS      "http://raft_groups_2:8808,http://raft_groups_3:8809" "http://coordinator:8700" raft_data_groups1
run_node raft_users_1     8810 USUARIOS    "http://raft_users_2:8811,http://raft_users_3:8812" "http://coordinator:8700" raft_data_users1

echo "🎯 Lanzando coordinador principal..."
docker rm -f coordinator 2>/dev/null || true
docker run -d --name coordinator --network "$NETWORK" \
  -p 8700:8700 -p ${WS_PORT}:8767 \
  -e PYTHONPATH="/app:/app/backend" \
  -e SHARD_EVENTS_A_M="$(IFS=,; echo "${EVENTS_AM[*]}")" \
  -e SHARD_EVENTS_N_Z="$(IFS=,; echo "${EVENTS_NZ[*]}")" \
  -e SHARD_GROUPS="$(IFS=,; echo "${GROUPS[*]}")" \
  -e SHARD_USERS="$(IFS=,; echo "${USERS[*]}")" \
  agenda_backend uvicorn distributed.coordinator.router:app --host 0.0.0.0 --port 8700

echo "🎨 Lanzando frontend en Host A..."
docker rm -f frontend_a 2>/dev/null || true
docker run -d --name frontend_a --hostname frontend_a --network "$NETWORK" \
  -p ${FRONT_PORT}:8501 \
  -e PYTHONPATH="/app/front:/app" \
  -e API_BASE_URL=http://coordinator:8700 \
  -e WEBSOCKET_HOST=coordinator \
  -e WEBSOCKET_PORT=8767 \
  agenda_frontend streamlit run front/app.py --server.port=8501 --server.address=0.0.0.0

echo "✅ Host A listo. Front: http://${SELF_IP}:${FRONT_PORT}"
