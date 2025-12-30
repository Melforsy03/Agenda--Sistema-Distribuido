#!/usr/bin/env bash
set -euo pipefail

# Detiene y elimina los contenedores usados en el Host A.

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
    docker rm "$name" >/dev/null 2>&1 || true
    echo "Eliminado $name"
  else
    echo "$name no existe, se omite."
  fi
}

echo "Deteniendo contenedores del Host A..."
for c in "${containers[@]}"; do
  stop_container "$c"
done

echo "Host A limpio: contenedores detenidos y eliminados."
