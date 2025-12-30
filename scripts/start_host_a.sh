#!/usr/bin/env bash
set -euo pipefail

# Arranca el host A: coordinador principal + frontend + nodos base.
# Requiere que HOST_B_IP apunte al otro host.
#
# Opcionales:
#   NETWORK     (default agenda_net)
#   FRONT_PORT  (default 8501)
#   WS_PORT     (default 8768, mapea al 8767 interno del coordinador)

# Limpiar posibles configs sucias de shards en el entorno
unset SHARDS_CONFIG_JSON SHARD_GROUPS SHARD_GRUPOS SHARD_USERS SHARD_USUARIOS
unset SHARD_EVENTOS_A_M SHARD_EVENTOS_N_Z SHARD_EVENTS_A_M SHARD_EVENTS_N_Z

# Parar y eliminar contenedores previos que vamos a reutilizar (solo 3 nodos por shard en total)
docker rm -f coordinator frontend_a \
  raft_events_am_1 raft_events_am_2 \
  raft_events_nz_1 raft_events_nz_2 \
  raft_groups_1 \
  raft_users_1 2>/dev/null || true

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

# Config: 3 nodos por shard distribuidos entre hosts A/B
EVENTS_AM_NAMES=(raft_events_am_1 raft_events_am_2 raft_events_am_3)
EVENTS_AM_PORTS=(8801 8802 8803)
EVENTS_NZ_NAMES=(raft_events_nz_1 raft_events_nz_2 raft_events_nz_3)
EVENTS_NZ_PORTS=(8804 8805 8806)
GROUPS_NAMES=(raft_groups_1 raft_groups_2 raft_groups_3)
GROUPS_PORTS=(8807 8808 8809)
USERS_NAMES=(raft_users_1 raft_users_2 raft_users_3)
USERS_PORTS=(8810 8811 8812)

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

echo "🚀 Lanzando nodos en Host A (nodos 1-2 por shard)..."
for i in 0 1; do
  peers=$(peers_for EVENTS_AM_NAMES EVENTS_AM_PORTS "$i")
  run_node "${EVENTS_AM_NAMES[$i]}" "${EVENTS_AM_PORTS[$i]}" EVENTOS_A_M "$peers" "http://coordinator:8700" "raft_data_am$((i+1))"
done
for i in 0 1; do
  peers=$(peers_for EVENTS_NZ_NAMES EVENTS_NZ_PORTS "$i")
  run_node "${EVENTS_NZ_NAMES[$i]}" "${EVENTS_NZ_PORTS[$i]}" EVENTOS_N_Z "$peers" "http://coordinator:8700" "raft_data_nz$((i+1))"
done
run_node "${GROUPS_NAMES[0]}" "${GROUPS_PORTS[0]}" GRUPOS "$(peers_for GROUPS_NAMES GROUPS_PORTS 0)" "http://coordinator:8700" "raft_data_groups1"
run_node "${USERS_NAMES[0]}"  "${USERS_PORTS[0]}"  USUARIOS "$(peers_for USERS_NAMES USERS_PORTS 0)" "http://coordinator:8700" "raft_data_users1"

echo "🎯 Lanzando coordinador principal..."
docker rm -f coordinator 2>/dev/null || true
docker run -d --name coordinator --network "$NETWORK" \
  -p 8700:8700 -p ${WS_PORT}:8767 \
  -e PYTHONPATH="/app:/app/backend" \
  -e SHARDS_CONFIG_JSON="" \
  -e SHARD_EVENTOS_A_M="$(IFS=,; echo http://raft_events_am_1:8801,http://raft_events_am_2:8802,http://raft_events_am_3:8803)" \
  -e SHARD_EVENTOS_N_Z="$(IFS=,; echo http://raft_events_nz_1:8804,http://raft_events_nz_2:8805,http://raft_events_nz_3:8806)" \
  -e SHARD_GROUPS="$(IFS=,; echo http://raft_groups_1:8807,http://raft_groups_2:8808,http://raft_groups_3:8809)" \
  -e SHARD_USERS="$(IFS=,; echo http://raft_users_1:8810,http://raft_users_2:8811,http://raft_users_3:8812)" \
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
