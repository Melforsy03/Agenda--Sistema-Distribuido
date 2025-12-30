#!/usr/bin/env bash
set -euo pipefail

# Detiene los contenedores usados en el Host A.
# Usa --remove si también quieres eliminarlos tras detenerlos.

REMOVE="${1:-}"  # --remove para borrar contenedores tras stop
if [[ -n "$REMOVE" && "$REMOVE" != "--remove" ]]; then
  echo "Uso: $0 [--remove]" >&2
  exit 1
fi

containers=(
  coordinator
  frontend_a
  raft_events_am_1
  raft_events_am_2
  raft_events_am_3
  raft_events_nz_1
  raft_events_nz_2
  raft_events_nz_4
  raft_groups_1
  raft_users_1
)

stop_container() {
  local name="$1"
  if docker ps -a --format '{{.Names}}' | grep -Fxq "$name"; then
    echo "Deteniendo $name..."
    docker stop "$name" >/dev/null 2>&1 || true
    if [[ "$REMOVE" == "--remove" ]]; then
      docker rm "$name" >/dev/null 2>&1 || true
      echo "Eliminado $name"
    fi
  else
    echo "$name no existe, se omite."
  fi
}

echo "Deteniendo contenedores del Host A..."
for c in "${containers[@]}"; do
  stop_container "$c"
done

echo "Host A limpio. Usa --remove para borrarlos también."
