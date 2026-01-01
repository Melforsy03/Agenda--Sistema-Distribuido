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
COORD_A_URL=${COORD_A_URL:-http://${COORD_IP}:8700}
COORD_LB_URL=${COORD_LB_URL:-${COORD_B_URL:-http://coordinator_b:8700}}
LB_HOST=$(echo "$COORD_LB_URL" | sed -E 's#^https?://([^/:]+).*#\1#')
LB_PORT=$(echo "$COORD_LB_URL" | sed -nE 's#^https?://[^/:]+:([0-9]+).*#\1#p')
LB_PORT=${LB_PORT:-8700}
WS_PORT=${WS_PORT:-8769}
# API interno para el contenedor frontend: si COORD_LB_URL usa localhost/127.*, dentro del contenedor no sirve.
API_BASE_URL_CONTAINER="$COORD_LB_URL"
if [[ "$LB_HOST" =~ ^(localhost|127\\.|::1)$ ]]; then
  API_BASE_URL_CONTAINER="http://coordinator_b:8700"
  echo "ℹ️ COORD_LB_URL usa localhost; dentro del contenedor se usará ${API_BASE_URL_CONTAINER}"
fi

# Parar y eliminar contenedores previos usados por este host (solo nodos 3 por shard)
docker rm -f coordinator_b frontend_b \
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
SELF_COORD_URL=${SELF_COORD_URL:-http://${SELF_IP}:8701}
# Lista de coordinadores conocidos (agrega extra con EXTRA_COORD_PEERS si quieres más)
PEER_LIST=${EXTRA_COORD_PEERS:-}
if [[ -n "$COORD_A_URL" ]]; then
  PEER_LIST="${COORD_A_URL}${PEER_LIST:+,${PEER_LIST}}"
fi
COORD_B_URL=${COORD_B_URL:-http://coordinator_b:8700}
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
run_node "${EVENTS_AM_NAMES[2]}" "${EVENTS_AM_PORTS[2]}" EVENTOS_A_M "$peers" "$COORD_B_URL" "${COORD_B_URL},${COORD_A_URL}"

peers=$(peers_for EVENTS_NZ_NAMES EVENTS_NZ_PORTS 2)
run_node "${EVENTS_NZ_NAMES[2]}" "${EVENTS_NZ_PORTS[2]}" EVENTOS_N_Z "$peers" "$COORD_B_URL" "${COORD_B_URL},${COORD_A_URL}"

peers=$(peers_for GROUPS_NAMES GROUPS_PORTS 2)
run_node "${GROUPS_NAMES[2]}" "${GROUPS_PORTS[2]}" GRUPOS "$peers" "$COORD_B_URL" "${COORD_B_URL},${COORD_A_URL}"

peers=$(peers_for USERS_NAMES USERS_PORTS 2)
run_node "${USERS_NAMES[2]}" "${USERS_PORTS[2]}" USUARIOS "$peers" "$COORD_B_URL" "${COORD_B_URL},${COORD_A_URL}"

echo "🎯 Lanzando coordinador B..."
docker rm -f coordinator_b 2>/dev/null || true
docker run -d --name coordinator_b --network "$NETWORK" \
  -p 8701:8700 \
  -p ${WS_PORT}:8767 \
  -e PYTHONPATH="/app:/app/backend" \
  -e SHARDS_CONFIG_JSON="" \
  -e COORD_PEERS="${PEER_LIST}" \
  -e DISABLE_DEFAULT_SHARDS=1 \
  -e SELF_COORD_URL="$SELF_COORD_URL" \
  -l 'traefik.enable=true' \
  -l "traefik.docker.network=$NETWORK" \
  -l 'traefik.http.routers.coordinator.rule=PathPrefix(`/`)' \
  -l 'traefik.http.routers.coordinator.entrypoints=web' \
  -l 'traefik.http.services.coordinator.loadbalancer.server.port=8700' \
  agenda_backend uvicorn distributed.coordinator.router:app --host 0.0.0.0 --port 8700

echo "🎨 Lanzando frontend en Host B..."
docker rm -f frontend_b 2>/dev/null || true
docker run -d --name frontend_b --hostname frontend_b --network "$NETWORK" \
  -p ${FRONT_PORT}:8501 \
  -e PYTHONPATH="/app/front:/app" \
  -e API_BASE_URL=${API_BASE_URL_CONTAINER} \
  -e WEBSOCKET_HOST=${LB_HOST} \
  -e WEBSOCKET_PORT=${LB_PORT} \
  agenda_frontend streamlit run front/app.py --server.port=8501 --server.address=0.0.0.0

# Levantar siempre watcher + LB local con Traefik usando lista dinámica de coordinadores.
# Si COORD_LB_URL apunta directamente al coordinador (puerto 8700/8701), cambiamos LB_PORT a 8702 para no colisionar.
if [[ "$LB_PORT" == "8700" || "$LB_PORT" == "8701" ]]; then
  LB_PORT=8702
  echo "ℹ️ Ajustando LB_PORT a ${LB_PORT} para evitar colisión con coordinador."
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SERVERS_FILE=${SERVERS_FILE:-$(pwd)/servers.json}
SEEDS=${SEEDS:-"${COORD_A_URL},http://coordinator_b:8700"}
pkill -f "watch_coordinators.sh.*${SERVERS_FILE}" 2>/dev/null || true
# Crear archivo base para que start_lb use provider file desde el inicio
if [[ ! -f "$SERVERS_FILE" ]]; then
  cat >"$SERVERS_FILE" <<'EOF'
{
  "http": {
    "routers": {
      "coordinator": { "rule": "PathPrefix(`/`)", "service": "coordinators" }
    },
    "services": {
      "coordinators": { "loadBalancer": { "servers": [], "passHostHeader": true } }
    }
  }
}
EOF
fi
OUT="$SERVERS_FILE" SEEDS="$SEEDS" INTERVAL="${LB_WATCH_INTERVAL:-5}" bash "${SCRIPT_DIR}/watch_coordinators.sh" >/tmp/coord_watch_b.log 2>&1 &
for _ in {1..5}; do
  if [[ -s "$SERVERS_FILE" ]]; then break; fi
  sleep 1
done
STATIC_SERVERS_FILE="$SERVERS_FILE" LB_PORT="${LB_PORT:-8702}" NETWORK="$NETWORK" bash "${SCRIPT_DIR}/start_lb.sh"

echo "✅ Host B listo. Front: http://${SELF_IP}:${FRONT_PORT}"
