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
  raft_groups_1 raft_groups_2 \
  raft_users_1 raft_users_2 2>/dev/null || true

HOST_B_IP=${HOST_B_IP:-}
NETWORK=${NETWORK:-agenda_net}
FRONT_PORT=${FRONT_PORT:-8501}
WS_PORT=${WS_PORT:-8768}
COORD_B_URL=${COORD_B_URL:-http://coordinator_b:8700}
COORD_LB_URL=${COORD_LB_URL:-http://coordinator_lb:8700}
# Extra: host/puerto derivados de COORD_LB_URL para API/WS
LB_HOST=$(echo "$COORD_LB_URL" | sed -E 's#^https?://([^/:]+).*#\1#')
LB_PORT=$(echo "$COORD_LB_URL" | sed -nE 's#^https?://[^/:]+:([0-9]+).*#\1#p')
LB_PORT=${LB_PORT:-8700}
# API interno para el contenedor frontend
API_BASE_URL_CONTAINER="$COORD_LB_URL"
if [[ "$LB_HOST" =~ ^(localhost|127\\.|::1)$ ]]; then
  API_BASE_URL_CONTAINER="http://coordinator:8700"
  echo "ℹ️ COORD_LB_URL usa localhost; dentro del contenedor se usará ${API_BASE_URL_CONTAINER}"
fi

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
  local name=$1 port=$2 shard=$3 peers=$4 coord_url=$5 coord_urls=$6 volume=$7
  docker run -d --name "$name" --hostname "$name" --network "$NETWORK" -p "${port}:${port}" \
    -v "$volume":/app/data \
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

echo "🚀 Lanzando nodos en Host A (nodos 1-2 por shard)..."
for i in 0 1; do
  peers=$(peers_for EVENTS_AM_NAMES EVENTS_AM_PORTS "$i")
  run_node "${EVENTS_AM_NAMES[$i]}" "${EVENTS_AM_PORTS[$i]}" EVENTOS_A_M "$peers" "http://coordinator:8700" "http://coordinator:8700,${COORD_B_URL}" "raft_data_am$((i+1))"
done
for i in 0 1; do
  peers=$(peers_for EVENTS_NZ_NAMES EVENTS_NZ_PORTS "$i")
  run_node "${EVENTS_NZ_NAMES[$i]}" "${EVENTS_NZ_PORTS[$i]}" EVENTOS_N_Z "$peers" "http://coordinator:8700" "http://coordinator:8700,${COORD_B_URL}" "raft_data_nz$((i+1))"
done
for i in 0 1; do
  peers=$(peers_for GROUPS_NAMES GROUPS_PORTS "$i")
  run_node "${GROUPS_NAMES[$i]}" "${GROUPS_PORTS[$i]}" GRUPOS "$peers" "http://coordinator:8700" "http://coordinator:8700,${COORD_B_URL}" "raft_data_groups$((i+1))"
done
for i in 0 1; do
  peers=$(peers_for USERS_NAMES USERS_PORTS "$i")
  run_node "${USERS_NAMES[$i]}" "${USERS_PORTS[$i]}" USUARIOS "$peers" "http://coordinator:8700" "http://coordinator:8700,${COORD_B_URL}" "raft_data_users$((i+1))"
done

echo "🎯 Lanzando coordinador principal..."
docker rm -f coordinator 2>/dev/null || true
docker run -d --name coordinator --network "$NETWORK" \
  -p 8700:8700 -p ${WS_PORT}:8767 \
  -e PYTHONPATH="/app:/app/backend" \
  -e SHARDS_CONFIG_JSON="" \
  -e DISABLE_DEFAULT_SHARDS=1 \
  -l 'traefik.enable=true' \
  -l "traefik.docker.network=$NETWORK" \
  -l 'traefik.http.routers.coordinator.rule=PathPrefix(`/`)' \
  -l 'traefik.http.routers.coordinator.entrypoints=web' \
  -l 'traefik.http.services.coordinator.loadbalancer.server.port=8700' \
  agenda_backend uvicorn distributed.coordinator.router:app --host 0.0.0.0 --port 8700

echo "🎨 Lanzando frontend en Host A..."
docker rm -f frontend_a 2>/dev/null || true
docker run -d --name frontend_a --hostname frontend_a --network "$NETWORK" \
  -p ${FRONT_PORT}:8501 \
  -e PYTHONPATH="/app/front:/app" \
  -e API_BASE_URL=${API_BASE_URL_CONTAINER} \
  -e WEBSOCKET_HOST=${SELF_IP} \
  -e WEBSOCKET_PORT=${WS_PORT} \
  agenda_frontend streamlit run front/app.py --server.port=8501 --server.address=0.0.0.0

# Opcional: levantar watcher + LB local con Traefik usando lista dinámica de coordinadores
if [[ "${ENABLE_LB:-1}" == "1" ]]; then
  SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  SERVERS_FILE=${SERVERS_FILE:-$(pwd)/servers.json}
  SEEDS=${SEEDS:-"http://coordinator:8700,${COORD_B_URL}"}
  # Matar watcher previo si existe
  pkill -f "watch_coordinators.sh.*${SERVERS_FILE}" 2>/dev/null || true
  OUT="$SERVERS_FILE" SEEDS="$SEEDS" INTERVAL="${LB_WATCH_INTERVAL:-5}" bash "${SCRIPT_DIR}/watch_coordinators.sh" >/tmp/coord_watch_a.log 2>&1 &
  STATIC_SERVERS_FILE="$SERVERS_FILE" LB_PORT="${LB_PORT:-8702}" NETWORK="$NETWORK" bash "${SCRIPT_DIR}/start_lb.sh"
fi

echo "✅ Host A listo. Front: http://${SELF_IP}:${FRONT_PORT}"
