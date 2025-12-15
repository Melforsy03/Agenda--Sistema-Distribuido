#!/usr/bin/env bash
set -euo pipefail

# Agrega un nodo RAFT a un shard existente.
# Uso:
#   add_node.sh <SHARD_NAME> <NODE_ID> <PORT> <PEERS> <COORD_URL> [REPLICATION_FACTOR]
# Ejemplo:
#   add_node.sh EVENTOS_A_M raft_events_am_2 8802 http://raft_events_am_1:8801 http://coordinator:80 1
#
# Notas:
# - PEERS es coma-separado; si lo dejas vacío y AUTO_PEERS=1, intentará descubrir peers del coordinador.
# - COORD_URL permite autoregistro en el coordinador (/admin/shards/add) y descubrimiento de peers.
# - REPLICATION_FACTOR por defecto 1 (ajusta a 2 cuando haya 3 nodos).

if [[ $# -lt 5 ]]; then
  echo "Uso: $0 <SHARD_NAME> <NODE_ID> <PORT> <PEERS> <COORD_URL> [REPLICATION_FACTOR]" >&2
  exit 1
fi

SHARD_NAME=$1
NODE_ID=$2
PORT=$3
PEERS_RAW=$4
COORD_URL=$5
REPL=${6:-${DEFAULT_REPL:-2}}

NET=${NET:-agenda_net}
IMAGE=${IMAGE:-agenda_backend}
KEEP_EXISTING=${KEEP_EXISTING:-0}
EXPOSE_HOST=${EXPOSE_HOST:-1}  # si es 1, publica el puerto en localhost
AUTO_PEERS=${AUTO_PEERS:-1}    # si es 1 y no se pasan PEERS, intenta obtenerlos del coordinador

PEERS=""
if [[ -n "$PEERS_RAW" ]]; then
  PEERS="$PEERS_RAW"
fi

normalize_shard(){
  local k="${1,,}"
  case "$k" in
    eventos_a_m|events_a_m) echo "eventos_a_m" ;;
    eventos_n_z|events_n_z) echo "eventos_n_z" ;;
    grupos|groups) echo "groups" ;;
    usuarios|users) echo "users" ;;
    *) echo "$k" ;;
  esac
}

fetch_peers_from_coord(){
  local shard_key="$1"
  [[ -z "$COORD_URL" ]] && return
  local raw peers alt
  raw=$(curl -sS "${COORD_URL%/}/leaders" || true)
  peers=$(echo "$raw" | python3 - "$shard_key" <<'PY'
import sys, json
shard = sys.argv[1]
raw = sys.stdin.read().strip()
if not raw:
    sys.exit(1)
alt_map = {
    "eventos_a_m": "events_a_m",
    "events_a_m": "eventos_a_m",
    "eventos_n_z": "events_n_z",
    "events_n_z": "eventos_n_z",
    "groups": "grupos",
    "grupos": "groups",
    "users": "usuarios",
    "usuarios": "users",
}
try:
    data = json.loads(raw)
    keys = [shard]
    alt = alt_map.get(shard)
    if alt:
        keys.append(alt)
    for k in keys:
        if isinstance(data.get(k), dict):
            nodes = data[k].get("nodes") or []
            if nodes:
                print(",".join(nodes))
                sys.exit(0)
except Exception:
    pass
PY
  )
  if [[ -n "$peers" ]]; then
    # quitar self si estaba listado
    local filtered=""
    IFS=',' read -ra arr <<< "$peers"
    for p in "${arr[@]}"; do
      if [[ "$p" != "http://${NODE_ID}:${PORT}" ]]; then
        filtered+="${p},"
      fi
    done
    PEERS="${filtered%,}"
  fi
}

# Descubrir peers si no se pasaron y está habilitado AUTO_PEERS
if [[ -z "$PEERS" && "$AUTO_PEERS" == "1" ]]; then
  shard_key=$(normalize_shard "$SHARD_NAME")
  fetch_peers_from_coord "$shard_key"
fi

# Evitar conflictos de nombre
if docker ps -a --format '{{.Names}}' | grep -q "^${NODE_ID}$"; then
  if [[ "$KEEP_EXISTING" == "1" ]]; then
    echo "↩️  ${NODE_ID} ya existe, omito creación (KEEP_EXISTING=1)"
    exit 0
  else
    echo "♻️  Eliminando contenedor previo ${NODE_ID}..."
    docker rm -f "${NODE_ID}" >/dev/null 2>&1 || true
  fi
fi

echo "🚀 Agregando nodo $NODE_ID (shard $SHARD_NAME) en puerto $PORT"
EXPOSE_ARGS=()
if [[ "$EXPOSE_HOST" == "1" ]]; then
  EXPOSE_ARGS=(-p "${PORT}:${PORT}")
fi

docker run -d --name "$NODE_ID" --hostname "$NODE_ID" --network "$NET" "${EXPOSE_ARGS[@]}" \
  -e SHARD_NAME="$SHARD_NAME" \
  -e NODE_ID="$NODE_ID" \
  -e NODE_URL="http://${NODE_ID}:${PORT}" \
  -e PORT="$PORT" \
  -e PEERS="$PEERS" \
  -e REPLICATION_FACTOR="$REPL" \
  -e COORD_URL="$COORD_URL" \
  "$IMAGE" uvicorn distributed.nodes.raft_node:app --host 0.0.0.0 --port "$PORT"

echo "✅ Nodo $NODE_ID lanzado. Si COORD_URL es accesible, se autoregistrará en el coordinador."
