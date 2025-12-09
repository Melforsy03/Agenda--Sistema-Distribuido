#!/bin/bash
set -euo pipefail

# Script de caos controlado para poner a prueba la tolerancia a fallos.
# Ejecutar despues de desplegar con deploy_swarn.sh. Usa docker stop/kill
# para simular caidas y desconexiones sin borrar datos.

NETWORK_NAME=${NETWORK_NAME:-agenda_net}
BACKEND_CONTAINER=${BACKEND_CONTAINER:-backend}
COORDINATOR_CONTAINER=${COORDINATOR_CONTAINER:-coordinator}
FRONTEND_CONTAINER=${FRONTEND_CONTAINER:-frontend}
# Forzamos RAFT_NODES a un array aunque venga como string con espacios o con comillas.
RAFT_NODES_STRING=${RAFT_NODES:-"raft_events_am_1 raft_events_am_2 raft_events_am_3 raft_events_nz_1 raft_events_nz_2 raft_events_nz_3 raft_groups_1 raft_groups_2 raft_groups_3 raft_users_1 raft_users_2 raft_users_3"}
IFS=' ' read -r -a RAFT_NODES <<< "$RAFT_NODES_STRING"
SLEEP_BETWEEN=${SLEEP_BETWEEN:-6}
SLEEP_MAJOR=${SLEEP_MAJOR:-12}

log() { printf "\033[1;36m%s\033[0m\n" "$1"; }
warn() { printf "\033[1;33m%s\033[0m\n" "$1"; }

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    warn "Falta el binario requerido: $1"
    exit 1
  fi
}

exists_container() {
  docker container inspect "$1" >/dev/null 2>&1
}

stop_soft() {
  local c=$1
  if exists_container "$c"; then
    log "Parando (graceful) $c ..."
    docker stop -t 5 "$c" >/dev/null 2>&1 || true
  else
    warn "Contenedor $c no encontrado; se omite."
  fi
}

kill_hard() {
  local c=$1
  if exists_container "$c"; then
    log "Matando (SIGKILL) $c ..."
    docker kill "$c" >/dev/null 2>&1 || true
  else
    warn "Contenedor $c no encontrado; se omite."
  fi
}

start_up() {
  local c=$1
  if exists_container "$c"; then
    log "Arrancando $c ..."
    docker start "$c" >/dev/null 2>&1 || true
  else
    warn "Contenedor $c no encontrado; se omite."
  fi
}

disconnect_net() {
  local c=$1
  if exists_container "$c"; then
    log "Desconectando $c de la red $NETWORK_NAME ..."
    docker network disconnect -f "$NETWORK_NAME" "$c" >/dev/null 2>&1 || warn "Fallo al desconectar $c"
  else
    warn "Contenedor $c no encontrado; se omite desconexion."
  fi
}

reconnect_net() {
  local c=$1
  if exists_container "$c"; then
    log "Reconectando $c a la red $NETWORK_NAME ..."
    docker network connect "$NETWORK_NAME" "$c" >/dev/null 2>&1 || warn "Fallo al reconectar $c"
  else
    warn "Contenedor $c no encontrado; se omite reconexion."
  fi
}

scenario_restart_one_per_shard() {
  log "Escenario 1: reinicio de un nodo en cada shard (pierde lider si coincide)."
  for node in raft_events_am_1 raft_events_nz_1 raft_groups_1 raft_users_1; do
    kill_hard "$node"
    sleep "$SLEEP_BETWEEN"
    start_up "$node"
    sleep "$SLEEP_BETWEEN"
  done
}

scenario_loss_of_majority() {
  log "Escenario 2: perdida de mayoria en un shard (dos nodos abajo)."
  local shard_nodes=(raft_events_am_1 raft_events_am_2 raft_events_am_3)
  for node in "${shard_nodes[@]:0:2}"; do
    kill_hard "$node"
  done
  log "Shard con 1 solo nodo. Espera para observar bloqueo de escrituras..."
  sleep "$SLEEP_MAJOR"
  for node in "${shard_nodes[@]:0:2}"; do
    start_up "$node"
    sleep "$SLEEP_BETWEEN"
  done
}

scenario_coordinator_backend_outage() {
  log "Escenario 3: caida del backend y coordinador a la vez."
  kill_hard "$COORDINATOR_CONTAINER"
  kill_hard "$BACKEND_CONTAINER"
  sleep "$SLEEP_MAJOR"
  start_up "$BACKEND_CONTAINER"
  sleep "$SLEEP_BETWEEN"
  start_up "$COORDINATOR_CONTAINER"
  sleep "$SLEEP_BETWEEN"
}

scenario_network_partition() {
  log "Escenario 4: particion de red de un nodo RAFT."
  local node=${RAFT_NODES[4]:-raft_node5}
  disconnect_net "$node"
  sleep "$SLEEP_MAJOR"
  reconnect_net "$node"
  sleep "$SLEEP_BETWEEN"
}

scenario_chaos_burst() {
  log "Escenario 5: racha de caidas aleatorias en nodos RAFT."
  local rounds=${1:-5}
  for i in $(seq 1 "$rounds"); do
    local target
    target=$(printf "%s\n" "${RAFT_NODES[@]}" | shuf -n 1)
    kill_hard "$target"
    sleep 3
    start_up "$target"
    sleep 2
  done
}

usage() {
  cat <<EOF
Uso: $(basename "$0") [escenario]

Escenarios disponibles:
  all                   Ejecuta todos en serie.
  restart-per-shard     Reinicia un nodo por shard.
  loss-majority         Baja 2 nodos del shard de eventos A-M.
  coord-backend-down    Tumbar coordinador y backend a la vez.
  net-partition         Desconecta un nodo de la red overlay y lo reconecta.
  chaos-burst [n]       Caidas aleatorias n veces (default 5).

Variables ajustables:
  NETWORK_NAME, BACKEND_CONTAINER, COORDINATOR_CONTAINER, FRONTEND_CONTAINER,
  RAFT_NODES, SLEEP_BETWEEN, SLEEP_MAJOR.
EOF
}

main() {
  require docker

  local scenario=${1:-all}
  case "$scenario" in
    restart-per-shard) scenario_restart_one_per_shard ;;
    loss-majority) scenario_loss_of_majority ;;
    coord-backend-down) scenario_coordinator_backend_outage ;;
    net-partition) scenario_network_partition ;;
    chaos-burst) scenario_chaos_burst "${2:-5}" ;;
    all)
      scenario_restart_one_per_shard
      scenario_loss_of_majority
      scenario_coordinator_backend_outage
      scenario_network_partition
      scenario_chaos_burst 5
      ;;
    *) usage; exit 1 ;;
  esac

  log "Listo. Revisa logs/metricas para validar comportamiento."
}

main "$@"
