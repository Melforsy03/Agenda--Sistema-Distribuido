#!/usr/bin/env bash
set -euo pipefail

# Monitor liviano que consulta /raft/state de todos los nodos y muestra rol/termino/lider.
# Uso: bash tests/monitor_raft_state.sh [intervalo_segundos]

INTERVAL=${1:-5}
NODES=${NODES:-"http://localhost:8801 http://localhost:8802 http://localhost:8803 http://localhost:8804 http://localhost:8805 http://localhost:8806 http://localhost:8807 http://localhost:8808 http://localhost:8809 http://localhost:8810 http://localhost:8811 http://localhost:8812"}

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Falta $1"
    exit 1
  fi
}

require curl
require python3

print_header() {
  printf "\n=== %s ===\n" "$(date +"%Y-%m-%d %H:%M:%S")"
  printf "%-24s %-8s %-8s %-25s\n" "NODO" "ROL" "TERM" "LIDER"
}

print_state() {
  python3 - "$@" <<'PY'
import json, sys
for url in sys.argv[1:]:
    try:
        import urllib.request
        with urllib.request.urlopen(url + "/raft/state", timeout=2) as r:
            data = json.loads(r.read().decode("utf-8"))
        role = data.get("role", "unknown")
        term = data.get("term", "?")
        leader = data.get("leader", "n/a")
        node = data.get("node_id", url)
        shard = data.get("shard", "")
        print(f"{node} ({shard})".ljust(24), role.ljust(8), str(term).ljust(8), str(leader))
    except Exception as e:
        print(url.ljust(24), "ERROR".ljust(8), "-", f"{e}")
PY
}

while true; do
  print_header
  print_state $NODES
  sleep "$INTERVAL"
done

