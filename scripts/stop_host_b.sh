#!/usr/bin/env bash
set -euo pipefail

# Detiene los contenedores usados en el Host B.
# Usa --remove si también quieres eliminarlos tras detenerlos.

REMOVE="${1:-}"  # --remove para borrar contenedores tras stop
if [[ -n "$REMOVE" && "$REMOVE" != "--remove" ]]; then
  echo "Uso: $0 [--remove]" >&2
  exit 1
fi

containers=(
  frontend_b
  raft_events_nz_3
  raft_events_nz_4
  raft_groups_2
  raft_groups_3
  raft_users_2
  raft_users_3
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

echo "Deteniendo contenedores del Host B..."
for c in "${containers[@]}"; do
  stop_container "$c"
done

echo "Host B limpio. Usa --remove para borrarlos también."
