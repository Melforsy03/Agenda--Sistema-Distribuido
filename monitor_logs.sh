#!/bin/bash
set -euo pipefail

# Muestra logs en vivo con prefijo de contenedor.
# Usar en paralelo con failover_scenarios.sh para observar reelecciones y errores.

DEFAULT_CONTAINERS="backend coordinator frontend raft_events_am_1 raft_events_am_2 raft_events_am_3 raft_events_nz_1 raft_events_nz_2 raft_events_nz_3 raft_groups_1 raft_groups_2 raft_groups_3 raft_users_1 raft_users_2 raft_users_3"
CONTAINERS_STRING=${CONTAINERS:-$DEFAULT_CONTAINERS}
IFS=' ' read -r -a CONTAINERS <<< "$CONTAINERS_STRING"
SINCE=${SINCE:-30s}  # ventana inicial de logs (p.ej. 5m, 1h, 0s)

log() { printf "\033[1;36m%s\033[0m\n" "$1"; }
warn() { printf "\033[1;33m%s\033[0m\n" "$1"; }

exists_container() {
  docker container inspect "$1" >/dev/null 2>&1
}

trap 'log "Saliendo, parando tails..."; for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done' INT TERM EXIT

PIDS=()
for c in "${CONTAINERS[@]}"; do
  if exists_container "$c"; then
    log "Siguiendo logs de $c (since=$SINCE)..."
    # shellcheck disable=SC2001
    docker logs -f --since "$SINCE" "$c" 2>&1 | sed "s/^/[$c] /" &
    PIDS+=($!)
  else
    warn "Contenedor $c no encontrado; se omite."
  fi
done

if [ ${#PIDS[@]} -eq 0 ]; then
  warn "No se esta siguiendo ningun contenedor."
  exit 1
fi

wait "${PIDS[@]}"
