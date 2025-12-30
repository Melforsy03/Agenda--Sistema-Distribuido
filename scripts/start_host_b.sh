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

# Parar y eliminar contenedores previos usados por este host (solo nodos 3 por shard)
docker rm -f frontend_b \
  raft_events_am_3 \
  raft_events_nz_3 \
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

EVENTS_AM_NAMES=(raft_events_am_1 raft_events_am_2 raft_events_am_3)
EVENTS_AM_PORTS=(8801 8802 8803)
EVENTS_NZ_NAMES=(raft_events_nz_1 raft_events_nz_2 raft_events_nz_3)
EVENTS_NZ_PORTS=(8804 8805 8806)
GROUPS_NAMES=(raft_groups_1 raft_groups_2 raft_groups_3)
GROUPS_PORTS=(8807 8808 8809)
USERS_NAMES=(raft_users_1 raft_users_2 raft_users_3)
USERS_PORTS=(8810 8811 8812)

run_node() {
  local name=$1 port=$2 shard=$3 peers=$4 coord_url=$5 coord_urls=$6
  docker run -d --name "$name" --hostname "$name" --network "$NETWORK" -p "${port}:${port}" \
    -v "${name}_data":/app/data \
    -e PYTHONPATH="/app:/app/backend" \
    -e SHARD_NAME="$shard" \
    -e NODE_ID="$name" \
    -e NODE_URL="http://${name}:${port}" \
    -e PORT="$port" \
    -e PEERS="$peers" \
    -e COORD_URL="$coord_url" \
    -e COORD_URLS="$coord_urls" \
    agenda_backend uvicorn distributed.nodes.raft_node:app --host 0.0.0.0 --port "$port"
}

peers_for() {
  local -n names=$1 ports=$2
  local idx=$3
  local peers=()
  for j in "${!names[@]}"; do
    if [[ $j -ne $idx ]]; then
      peers+=("http://${names[$j]}:${ports[$j]}")
    fi
  done
  IFS=,; echo "${peers[*]}"
}

echo "🚀 Lanzando nodos en Host B (nodo 3 por shard)..."
peers=$(peers_for EVENTS_AM_NAMES EVENTS_AM_PORTS 2)
run_node "${EVENTS_AM_NAMES[2]}" "${EVENTS_AM_PORTS[2]}" EVENTOS_A_M "$peers" "http://coordinator_b:8700" "http://coordinator_b:8700,http://coordinator:8700"

peers=$(peers_for EVENTS_NZ_NAMES EVENTS_NZ_PORTS 2)
run_node "${EVENTS_NZ_NAMES[2]}" "${EVENTS_NZ_PORTS[2]}" EVENTOS_N_Z "$peers" "http://coordinator_b:8700" "http://coordinator_b:8700,http://coordinator:8700"

peers=$(peers_for GROUPS_NAMES GROUPS_PORTS 2)
run_node "${GROUPS_NAMES[2]}" "${GROUPS_PORTS[2]}" GRUPOS "$peers" "http://coordinator_b:8700" "http://coordinator_b:8700,http://coordinator:8700"

peers=$(peers_for USERS_NAMES USERS_PORTS 2)
run_node "${USERS_NAMES[2]}" "${USERS_PORTS[2]}" USUARIOS "$peers" "http://coordinator_b:8700" "http://coordinator_b:8700,http://coordinator:8700"

echo "🎯 Lanzando coordinador B..."
docker rm -f coordinator_b 2>/dev/null || true
docker run -d --name coordinator_b --network "$NETWORK" \
  -p 8701:8700 \
  -e PYTHONPATH="/app:/app/backend" \
  -e SHARDS_CONFIG_JSON="" \
  -e SHARD_EVENTOS_A_M="$(IFS=,; echo http://raft_events_am_1:8801,http://raft_events_am_2:8802,http://raft_events_am_3:8803)" \
  -e SHARD_EVENTOS_N_Z="$(IFS=,; echo http://raft_events_nz_1:8804,http://raft_events_nz_2:8805,http://raft_events_nz_3:8806)" \
  -e SHARD_GROUPS="$(IFS=,; echo http://raft_groups_1:8807,http://raft_groups_2:8808,http://raft_groups_3:8809)" \
  -e SHARD_USERS="$(IFS=,; echo http://raft_users_1:8810,http://raft_users_2:8811,http://raft_users_3:8812)" \
  agenda_backend uvicorn distributed.coordinator.router:app --host 0.0.0.0 --port 8700

echo "🎨 Lanzando frontend en Host B..."
docker rm -f frontend_b 2>/dev/null || true
docker run -d --name frontend_b --hostname frontend_b --network "$NETWORK" \
  -p ${FRONT_PORT}:8501 \
  -e PYTHONPATH="/app/front:/app" \
  -e API_BASE_URL=http://coordinator_b:8700 \
  -e WEBSOCKET_HOST=coordinator_b \
  -e WEBSOCKET_PORT=8767 \
  agenda_frontend streamlit run front/app.py --server.port=8501 --server.address=0.0.0.0

echo "✅ Host B listo. Front: http://${SELF_IP}:${FRONT_PORT}"
