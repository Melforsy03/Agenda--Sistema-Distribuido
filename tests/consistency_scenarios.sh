#!/usr/bin/env bash
set -euo pipefail

# Orquesta escenarios rápidos de consistencia:
#  1) Inserta/valida dataset (usa consistency_suite.sh).
#  2) Reinicia un nodo de cada shard.
#  3) Inserta/valida de nuevo tras los reinicios.
#
# Variables:
#   COORD_URL (default http://localhost:8700)
#   NODES_AM_RESTART (default raft_events_am_1)
#   NODES_NZ_RESTART (default raft_events_nz_1)
#   NODES_GROUPS_RESTART (default raft_groups_1)
#   NODES_USERS_RESTART (default raft_users_1)
#   SLEEP_RESTART (segundos, default 6)
#
# Requisitos: docker, curl, python3, y que tests/consistency_suite.sh sea ejecutable.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

COORD_URL=${COORD_URL:-http://localhost:8700}
NODES_AM_RESTART=${NODES_AM_RESTART:-raft_events_am_1}
NODES_NZ_RESTART=${NODES_NZ_RESTART:-raft_events_nz_1}
NODES_GROUPS_RESTART=${NODES_GROUPS_RESTART:-raft_groups_1}
NODES_USERS_RESTART=${NODES_USERS_RESTART:-raft_users_1}
SLEEP_RESTART=${SLEEP_RESTART:-6}

SUITE="${ROOT_DIR}/tests/consistency_suite.sh"

log() { printf "\033[1;36m%s\033[0m\n" "$1"; }
warn() { printf "\033[1;33m%s\033[0m\n" "$1"; }
err() { printf "\033[1;31m%s\033[0m\n" "$1"; }

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Falta el binario requerido: $1"
    exit 1
  fi
}

require docker
require curl
require python3

if [ ! -x "$SUITE" ]; then
  err "No se encuentra o no es ejecutable: $SUITE"
  exit 1
fi

restart_node() {
  local c=$1
  log "Reiniciando ${c} ..."
  docker restart "$c" >/dev/null 2>&1 || warn "No se pudo reiniciar ${c}"
  sleep "$SLEEP_RESTART"
}

run_suite() {
  log "Ejecutando consistency_suite (COORD_URL=${COORD_URL})..."
  COORD_URL="$COORD_URL" "$SUITE"
}

main() {
  log "== Escenario de consistencia: baseline =="
  run_suite

  log "== Reinicio de un nodo por shard =="
  restart_node "$NODES_AM_RESTART"
  restart_node "$NODES_NZ_RESTART"
  restart_node "$NODES_GROUPS_RESTART"
  restart_node "$NODES_USERS_RESTART"

  log "== Validación post-reinicio =="
  run_suite

  log "✅ Escenario completado. Revisa logs/monitoreo en paralelo si quieres más detalle."
}

main "$@"

