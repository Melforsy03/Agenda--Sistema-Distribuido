#!/usr/bin/env bash
set -euo pipefail

# Suite de pruebas de consistencia/replicación vía coordinador y nodos RAFT.
# Crea datos sintéticos en cada shard y valida que aparezcan en TODOS los nodos.
# Requisitos: curl, python3. Opcional: jq para inspección manual.

COORD_URL=${COORD_URL:-http://localhost:8700}
EVENTS_AM_NODES=${EVENTS_AM_NODES:-"http://localhost:8801 http://localhost:8802 http://localhost:8803"}
EVENTS_NZ_NODES=${EVENTS_NZ_NODES:-"http://localhost:8804 http://localhost:8805 http://localhost:8806"}
GROUP_NODES=${GROUP_NODES:-"http://localhost:8807 http://localhost:8808 http://localhost:8809"}
USER_NODES=${USER_NODES:-"http://localhost:8810 http://localhost:8811 http://localhost:8812"}

NUM_EVENTS_PER_SHARD=${NUM_EVENTS_PER_SHARD:-5}
NUM_GROUPS=${NUM_GROUPS:-3}
NUM_USERS=${NUM_USERS:-4}

TMP_DIR=${TMP_DIR:-/tmp/agenda_consistency}
mkdir -p "$TMP_DIR"

log() { printf "\033[1;36m%s\033[0m\n" "$1"; }
warn() { printf "\033[1;33m%s\033[0m\n" "$1"; }
err() { printf "\033[1;31m%s\033[0m\n" "$1"; }

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Falta el binario requerido: $1"
    exit 1
  fi
}

require curl
require python3

timestamp() { date +"%Y%m%d%H%M%S"; }
TS=$(timestamp)

EVENTS_AM_TITLES=()
EVENTS_NZ_TITLES=()
GROUP_NAMES=()
USER_NAMES=()

post_json() {
  local url=$1 payload=$2
  local code
  code=$(curl -sS -w "%{http_code}" -o /dev/null -X POST "$url" -H "Content-Type: application/json" -d "$payload" || echo "curl_err")
  echo "$code"
}

create_users() {
  log "Creando ${NUM_USERS} usuarios de prueba..."
  for i in $(seq 1 "$NUM_USERS"); do
    local username="u${i}_${TS}"
    local email="${username}@test.local"
    USER_NAMES+=("$username")
    local code
    code=$(post_json "${COORD_URL}/users" "{\"username\":\"${username}\",\"email\":\"${email}\"}")
    if [ "$code" != "200" ]; then
      warn "Fallo al crear usuario ${username} (HTTP ${code})"
    fi
  done
}

create_events() {
  log "Creando eventos shard A-M..."
  for i in $(seq 1 "$NUM_EVENTS_PER_SHARD"); do
    local title="evt_am_${TS}_${i}"
    EVENTS_AM_TITLES+=("$title")
    local code
    code=$(post_json "${COORD_URL}/events" "{\"title\":\"${title}\",\"description\":\"demo\",\"creator\":\"ana_${TS}\",\"start_time\":\"2025-12-01 10:00\",\"end_time\":\"2025-12-01 11:00\"}")
    if [ "$code" != "200" ]; then
      warn "Fallo al crear ${title} (HTTP ${code})"
    fi
  done

  log "Creando eventos shard N-Z..."
  for i in $(seq 1 "$NUM_EVENTS_PER_SHARD"); do
    local title="evt_nz_${TS}_${i}"
    EVENTS_NZ_TITLES+=("$title")
    local code
    code=$(post_json "${COORD_URL}/events" "{\"title\":\"${title}\",\"description\":\"demo\",\"creator\":\"zoe_${TS}\",\"start_time\":\"2025-12-02 10:00\",\"end_time\":\"2025-12-02 11:00\"}")
    if [ "$code" != "200" ]; then
      warn "Fallo al crear ${title} (HTTP ${code})"
    fi
  done
}

create_groups() {
  log "Creando ${NUM_GROUPS} grupos de prueba..."
  for i in $(seq 1 "$NUM_GROUPS"); do
    local name="grp_${TS}_${i}"
    GROUP_NAMES+=("$name")
    local code
    code=$(post_json "${COORD_URL}/groups" "{\"name\":\"${name}\",\"description\":\"grupo demo\",\"creator\":\"system\"}")
    if [ "$code" != "200" ]; then
      warn "Fallo al crear grupo ${name} (HTTP ${code})"
    fi
  done
}

contains_all() {
  # DATA env var: JSON array; args: elementos esperados
  local data="$1"; shift
  DATA="$data" python3 - "$@" <<'PY'
import json, sys, os
expected = sys.argv[1:]
try:
    text = os.environ.get("DATA", "").strip()
    if not text:
        raise ValueError("Respuesta vacia")
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("Respuesta no es lista JSON")
except Exception as e:
    sys.stderr.write(f"Error parseando JSON: {e}\n")
    sys.exit(2)

present = set()
for item in data:
    for key in ("title", "name", "username"):
        if key in item:
            present.add(item[key])
missing = [x for x in expected if x not in present]
if missing:
    sys.stderr.write("Faltan: " + ", ".join(missing) + "\n")
    sys.exit(1)
PY
}

verify_shard() {
  local label=$1 path=$2 expected_items=("${!3}") nodes=(${!4})
  log "Verificando replicacion en shard ${label} (${#nodes[@]} nodos)..."
  local attempt max_attempts
  max_attempts=${MAX_RETRIES:-3}
  for n in "${nodes[@]}"; do
    # Para events pedimos los ultimos elementos para que incluya los recien creados.
    local url="${n}/${path}"
    if [ "$path" = "events" ]; then
      url="${n}/${path}?order=desc&limit=500"
    fi
    attempt=1
    while :; do
      local tmp http_code resp
      tmp=$(mktemp)
      http_code=$(curl -sS --max-time "${CURL_TIMEOUT:-8}" -w "%{http_code}" -o "$tmp" "$url" || echo "curl_err")
      resp=$(cat "$tmp")
      len=$(printf "%s" "$resp" | wc -c)
      rm -f "$tmp"
      if [ "$http_code" = "curl_err" ]; then
        err "No se pudo leer ${url}"
        exit 2
      fi
      # Tratar como vacio si solo hay espacios/nuevas líneas
      if ! printf "%s" "$resp" | grep -q '[^[:space:]]'; then
        warn "Respuesta vacia desde ${url} (len=${len}), intento ${attempt}/${max_attempts}"
        if [ "$attempt" -ge "$max_attempts" ]; then
          err "Shard ${label}: sin respuesta en ${url}"
          exit 4
        fi
        sleep 1
        attempt=$((attempt + 1))
        continue
      fi
      if [ "$http_code" != "200" ]; then
        err "Shard ${label}: ${url} devolvio HTTP ${http_code}"
        echo "Respuesta cruda:" >&2
        echo "$resp" >&2
        exit 3
      fi
      if contains_all "$resp" "${expected_items[@]}"; then
        break
      fi
      rc=$?
      if [ "$rc" -eq 2 ]; then
        err "Shard ${label}: error parseando JSON de ${url}"
        echo "HTTP ${http_code}, bytes=${len}" >&2
        echo "Respuesta cruda (inicio):" >&2
        printf '%s\n' "$resp" | head -n 5 >&2
        exit 5
      fi
      if [ "$attempt" -ge "$max_attempts" ]; then
        err "Shard ${label}: faltan elementos en ${n} (${path})."
        echo "Ultima respuesta HTTP ${http_code}, bytes=${len}" >&2
        printf '%s\n' "$resp" | head -n 5 >&2
        exit 4
      fi
      sleep 1
      attempt=$((attempt + 1))
    done
  done
  log "Shard ${label}: OK (${path})"
}

main() {
  log "Iniciando suite de consistencia contra ${COORD_URL}"

  create_users
  create_events
  create_groups

  verify_shard "EVENTOS_A_M" "events" EVENTS_AM_TITLES[@] EVENTS_AM_NODES[@]
  verify_shard "EVENTOS_N_Z" "events" EVENTS_NZ_TITLES[@] EVENTS_NZ_NODES[@]
  verify_shard "GRUPOS" "groups" GROUP_NAMES[@] GROUP_NODES[@]
  verify_shard "USUARIOS" "users" USER_NAMES[@] USER_NODES[@]

  log "✅ Consistencia verificada: todos los nodos contienen los elementos creados."
  log "Sugerencia: ejecuta tests/failover_scenarios.sh + este script para validar bajo fallos."
}

main "$@"
