#!/usr/bin/env bash
set -euo pipefail

# Detiene y elimina los contenedores usados en el Host B.

containers=(
  frontend_b
  raft_events_am_3
  raft_events_nz_3
  raft_groups_2
  raft_groups_3
  raft_users_2
  raft_users_3
  coordinator2
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

echo "Deteniendo contenedores del Host B..."
for c in "${containers[@]}"; do
  stop_container "$c"
done

echo "Host B limpio: contenedores detenidos y eliminados."
