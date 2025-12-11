#!/usr/bin/env bash
set -euo pipefail

# Automatiza escenarios de failover y consistencia básicos:
# 1) Ejecuta consistency_suite como línea de base.
# 2) Simula caída del líder del shard EVENTOS_A_M, espera reelección,
#    crea un evento y verifica que aparece en los 3 nodos.
# 3) Simula caída de un follower del shard EVENTOS_A_M, crea un evento
#    y verifica replicación en los 3 nodos tras el rejoin.
#
# Requisitos:
# - curl, jq, docker
# - Cluster desplegado y accesible (coordinator en COORD_URL)

COORD_URL="${COORD_URL:-http://localhost:8700}"
EVENTS_NODES=("http://localhost:8801" "http://localhost:8802" "http://localhost:8803")
TITLE_PREFIX="evt_failover_$(date +%Y%m%d%H%M%S)"
CREATOR_AM="${CREATOR_AM:-ana_failover}"  # Debe mapear al shard A-M

require_bin() {
  command -v "$1" >/dev/null 2>&1 || { echo "❌ Necesito '$1' en PATH" >&2; exit 1; }
}

wait_for_leader() {
  local shard="$1" leader
  for _ in {1..60}; do
    leader=$(curl -sS "$COORD_URL/leaders" | jq -r --arg shard "$shard" '.[$shard].leader // .[$shard] // empty')
    # Evitar strings de error del coordinador ("No disponible", objetos serializados, etc.)
    if [[ -n "$leader" && "$leader" != "null" && "$leader" != "No disponible" && "$leader" != "error" ]]; then
      echo "$leader"
      return 0
    fi
    # Fallback: consultar nodos directamente para evitar caché desactualizada del coordinador
    if [[ "$shard" == "events_a_m" ]]; then
      for url in "${EVENTS_NODES[@]}"; do
        role=$(curl -sS --max-time 2 "$url/raft/state" 2>/dev/null | jq -r '.role // empty')
        if [[ "$role" == "leader" ]]; then
          echo "$url"
          return 0
        fi
      done
    fi
    sleep 1
  done
  echo "❌ No se encontró líder para $shard" >&2
  exit 1
}

container_from_url() {
  # Extrae el nombre del contenedor a partir de una URL http://host:port
  local url="$1" hostport
  hostport=$(printf "%s" "$url" | sed -E 's@^[a-zA-Z]+://@@')
  hostport=${hostport%%/*}
  echo "${hostport%%:*}"
}

container_port() {
  case "$1" in
    raft_events_am_1) echo "8801" ;;
    raft_events_am_2) echo "8802" ;;
    raft_events_am_3) echo "8803" ;;
    *) echo "" ;;
  esac
}

create_event_via_coordinator() {
  local title="$1"
  curl -sS -X POST "$COORD_URL/events" \
    -H 'Content-Type: application/json' \
    -d "{\"title\":\"$title\",\"description\":\"failover test\",\"creator\":\"$CREATOR_AM\",\"start_time\":\"2025-12-01 10:00\",\"end_time\":\"2025-12-01 11:00\"}" \
    >/dev/null
}

check_event_in_node() {
  local node_url="$1" title="$2"
  curl -sS "$node_url/events?order=desc&limit=200" | jq -e --arg t "$title" 'map(.title) | index($t)' >/dev/null
}

wait_event_in_node() {
  local node_url="$1" title="$2" retries="${3:-5}" sleep_s="${4:-1}"
  local attempt
  for attempt in $(seq 1 "$retries"); do
    if check_event_in_node "$node_url" "$title"; then
      return 0
    fi
    sleep "$sleep_s"
  done
  return 1
}

verify_replication() {
  local title="$1"
  for url in "${EVENTS_NODES[@]}"; do
    if ! wait_event_in_node "$url" "$title"; then
      echo "❌ Falta evento $title en $url" >&2
      return 1
    fi
  done
  echo "✅ Evento $title presente en los 3 nodos EVENTOS_A_M"
}

baseline() {
  echo "== Baseline =="
  COORD_URL="$COORD_URL" ./consistency_suite.sh || true
}

scenario_leader_failover() {
  echo "== Caída de líder EVENTOS_A_M =="
  local leader_url leader_ct title
  leader_url=$(wait_for_leader "events_a_m")
  leader_ct=$(container_from_url "$leader_url")
  echo "Líder actual: $leader_ct ($leader_url)"

  if [[ -z "$leader_ct" || "$leader_ct" == "No disponible" ]]; then
    echo "❌ No hay líder identificable, no puedo simular caída" >&2
    return 1
  fi

  echo "🔪 Deteniendo $leader_ct"
  docker stop "$leader_ct" >/dev/null

  # Esperar a que el cluster elija nuevo líder
  new_leader=$(wait_for_leader "events_a_m")
  echo "Nuevo líder: $(container_from_url "$new_leader")"

  title="${TITLE_PREFIX}_leader"
  create_event_via_coordinator "$title"
  # Mientras el líder viejo está caído, validamos solo los nodos activos
  for url in "${EVENTS_NODES[@]}"; do
    if [[ "$url" == "http://localhost:$(container_port "$leader_ct")" ]]; then
      continue
    fi
    if ! wait_event_in_node "$url" "$title"; then
      echo "❌ Falta evento $title en $url" >&2
      return 1
    fi
  done

  echo "♻️ Arrancando de nuevo $leader_ct"
  docker start "$leader_ct" >/dev/null
  # Dar tiempo a sincronizar y verificar en los 3
  sleep 3
  verify_replication "$title"
}

scenario_follower_failover() {
  echo "== Caída de follower EVENTOS_A_M =="
  local leader leader_ct follower title
  leader=$(wait_for_leader "events_a_m")
  leader_ct=$(container_from_url "$leader")
  # escoge un follower distinto del líder
  for ct in raft_events_am_1 raft_events_am_2 raft_events_am_3; do
    [[ "$ct" != "$leader_ct" ]] || continue
    follower="$ct"
    break
  done
  echo "Follower elegido: $follower"

  echo "🔪 Deteniendo $follower"
  docker stop "$follower" >/dev/null
  sleep 3

  title="${TITLE_PREFIX}_follower"
  create_event_via_coordinator "$title"
  # Validar en los nodos activos (follower caído se omite)
  for url in "${EVENTS_NODES[@]}"; do
    if [[ "$url" == "http://localhost:$(container_port "$follower")" ]]; then
      continue
    fi
    if ! wait_event_in_node "$url" "$title"; then
      echo "❌ Falta evento $title en $url" >&2
      return 1
    fi
  done

  echo "♻️ Arrancando de nuevo $follower"
  docker start "$follower" >/dev/null
  sleep 3
  verify_replication "$title"
}

main() {
  require_bin curl
  require_bin jq
  require_bin docker

  pushd "$(dirname "$0")" >/dev/null
  baseline
  scenario_leader_failover
  scenario_follower_failover
  popd >/dev/null
  echo "🏁 Escenarios de failover completados"
}

main "$@"
