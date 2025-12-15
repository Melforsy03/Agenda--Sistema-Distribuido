#!/usr/bin/env bash
set -euo pipefail

# Prepara un cluster mínimo y lo escala a 3 nodos por shard antes de correr test_extreme.
# Variables:
#   COORD_URL   (default http://localhost:8700)
#   EXPOSE_HOST (default 1) publica puertos en localhost
#   REPL        (default 2) replication_factor usado al agregar nodos
#   SKIP_CLEAN  (default 0) si es 1 no elimina contenedores previos
#   SKIP_BUILD  (default 1) si es 0 reconstruye agenda_backend
#   DEPLOY_MIN  (default scripts/deploy_min.sh)
#   ADD_NODE_SCRIPT (default scripts/add_node.sh)

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

COORD_URL=${COORD_URL:-http://localhost:8700}           # usado desde el host
COORD_URL_DOCKER=${COORD_URL_DOCKER:-http://coordinator:80}  # usado por contenedores
EXPOSE_HOST=${EXPOSE_HOST:-1}
REPL=${REPL:-2}
SKIP_CLEAN=${SKIP_CLEAN:-0}
SKIP_BUILD=${SKIP_BUILD:-1}
DEPLOY_MIN=${DEPLOY_MIN:-scripts/deploy_min.sh}
ADD_NODE_SCRIPT=${ADD_NODE_SCRIPT:-scripts/add_node.sh}

wait_coord(){
  local tries=0
  until curl -sS "${COORD_URL}/health" >/dev/null 2>&1; do
    tries=$((tries+1))
    if [[ $tries -ge 60 ]]; then
      echo "❌ Coordinador no responde en ${COORD_URL}/health" >&2
      return 1
    fi
    sleep 1
  done
}

clean_containers(){
  docker rm -f raft_events_am_1 raft_events_am_2 raft_events_am_3 raft_events_am_4 \
    raft_events_nz_1 raft_events_nz_2 raft_events_nz_3 \
    raft_groups_1 raft_groups_2 raft_groups_3 \
    raft_users_1 raft_users_2 raft_users_3 \
    coordinator frontend backend 2>/dev/null || true
}

add_node(){
  local shard="$1" name="$2" port="$3" peer="$4"
  EXPOSE_HOST="$EXPOSE_HOST" "$ADD_NODE_SCRIPT" "$shard" "$name" "$port" "$peer" "$COORD_URL_DOCKER" "$REPL"
}

if [[ "$SKIP_CLEAN" != "1" ]]; then
  clean_containers
fi

if [[ "$SKIP_BUILD" == "0" ]]; then
  docker build -t agenda_backend -f Dockerfile.backend .
fi

# Semillas (1 nodo por shard)
EXPOSE_HOST="$EXPOSE_HOST" "$DEPLOY_MIN"
wait_coord

# Escalar a 3 nodos por shard usando el seed como peer común
add_node EVENTOS_A_M raft_events_am_2 8802 http://raft_events_am_1:8801
add_node EVENTOS_A_M raft_events_am_3 8803 http://raft_events_am_1:8801

add_node EVENTOS_N_Z raft_events_nz_2 8805 http://raft_events_nz_1:8804
add_node EVENTOS_N_Z raft_events_nz_3 8806 http://raft_events_nz_1:8804

add_node GRUPOS raft_groups_2 8808 http://raft_groups_1:8807
add_node GRUPOS raft_groups_3 8809 http://raft_groups_1:8807

add_node USUARIOS raft_users_2 8811 http://raft_users_1:8810
add_node USUARIOS raft_users_3 8812 http://raft_users_1:8810

echo "✅ Cluster listo. Ejecuta luego: USE_HOST_IP=1 ./scripts/test_extreme.sh"
