#!/usr/bin/env bash
# Analiza el estado del cluster después de ejecutar stress_extreme_scenarios.sh
# Requisitos: curl, jq, docker. Asume coordinador en COORD_URL.

set -euo pipefail

COORD_URL="${COORD_URL:-http://localhost:8700}"
DEFAULT_PORTS=("8801" "8802" "8803" "8804" "8805" "8806" "8807" "8808" "8809" "8810" "8811" "8812")

require_bin() {
  command -v "$1" >/dev/null 2>&1 || { echo "❌ Necesito '$1' en PATH" >&2; exit 1; }
}

banner() {
  echo
  echo "==== $* ===="
}

check_coordinator() {
  banner "Salud coordinador"
  curl -sS "$COORD_URL/health" | jq .

  banner "Líderes por shard"
  curl -sS "$COORD_URL/leaders" | jq .

  banner "Estado de cluster"
  curl -sS "$COORD_URL/cluster/status" | jq .
}

check_nodes_state() {
  banner "Estado /raft/state de nodos conocidos"
  for p in "${DEFAULT_PORTS[@]}"; do
    url="http://localhost:${p}"
    if curl -fsS "$url/raft/state" >/dev/null 2>&1; then
      echo "---- $url ----"
      curl -sS "$url/raft/state" | jq .
    fi
  done
}

search_events() {
  banner "Verificación de eventos generados por stress"
  local patterns=("evt_churn" "evt_no_quorum" "evt_recupera" "evt_nz_burst" "evt_replaced")
  for p in "${DEFAULT_PORTS[@]:0:3}"; do
    url="http://localhost:${p}"
    if curl -fsS "$url/events" >/dev/null 2>&1; then
      echo "-- Eventos en $url --"
      curl -sS "$url/events" | jq -r '.[].title' | grep -E "$(IFS="|"; echo "${patterns[*]}")" || echo "Sin coincidencias"
    fi
  done
}

logs_summary() {
  banner "Logs recientes de coordinador y nodos (ultimas 50 líneas)"
  local cts=("coordinator" "raft_events_am_1" "raft_events_am_2" "raft_events_am_3" \
             "raft_events_nz_1" "raft_events_nz_2" "raft_events_nz_3")
  for ct in "${cts[@]}"; do
    if docker ps -a --format '{{.Names}}' | grep -q "^${ct}$"; then
      echo "-- $ct --"
      docker logs --tail=50 "$ct" 2>/dev/null | tail -n 50
    fi
  done
}

main() {
  require_bin curl
  require_bin jq
  require_bin docker
  check_coordinator
  check_nodes_state
  search_events
  logs_summary
}

main "$@"
