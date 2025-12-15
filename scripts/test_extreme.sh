#!/usr/bin/env bash
set -euo pipefail

# Pruebas básicas y “extremas” del sistema distribuido.
# Requisitos: curl, python3, cluster corriendo con coordinador accesible.
#
# Config:
#   COORD_URL (default http://localhost:8700)
#   ADD_NODE_SCRIPT (default scripts/add_node.sh)

COORD_URL=${COORD_URL:-http://localhost:8700}
ADD_NODE_SCRIPT=${ADD_NODE_SCRIPT:-scripts/add_node.sh}
HA_COORD=${HA_COORD:-0}
COORD_B_PORT=${COORD_B_PORT:-8701}
COORD_B_URL=${COORD_B_URL:-http://localhost:${COORD_B_PORT}}
COORD_NEW_PORT=${COORD_NEW_PORT:-8702}
COORD_NEW_URL=${COORD_NEW_URL:-http://localhost:${COORD_NEW_PORT}}

ts(){ date +"%Y-%m-%d %H:%M:%S"; }
log(){ echo "[$(ts)] $*"; }
parse(){
  local key="$1"
  python3 -c '
import sys, json
key = sys.argv[1]
raw = sys.stdin.read().strip()
if not raw:
    print("")
    raise SystemExit(0)
try:
    data = json.loads(raw)
    if isinstance(data, dict):
        print(data.get(key, ""))
    else:
        print("")
except Exception:
    print("")
' "$key"
}
leaders_json(){ curl -sS "${COORD_URL}/leaders"; }
# Devuelve lista de shards o vacío si la salida no es JSON
shard_keys(){
  leaders_json | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print(" ".join(d.keys()))
except Exception:
    print("")
'
}
shard_nodes(){
  local shard="$1"
  leaders_json | python3 -c '
import sys, json
shard = sys.argv[1]
try:
    data = json.load(sys.stdin)
    nodes = data.get(shard, {}).get("nodes", [])
    print(" ".join(nodes))
except Exception:
    print("")
' "$shard"
}

resolve_node_url(){
  local node_url="$1"
  # Si estamos corriendo desde el host, exponemos puertos y consultamos por localhost
  if [[ "${USE_HOST_IP:-1}" == "1" ]]; then
    local port
    port=$(echo "$node_url" | sed -n 's#.*:\([0-9][0-9]*\)$#\1#p')
    if [[ -n "$port" ]]; then
      echo "http://localhost:${port}"
      return
    fi
  fi
  echo "$node_url"
}

check_replication(){
  local shard="$1"; local label="$2"
  local nodes; nodes=$(shard_nodes "$shard")
  if [[ -z "$nodes" ]]; then
    log "ℹ️  ${label}: shard ${shard} sin nodos reportados"
    return
  fi
  log "🔎 ${label}: rol y logs en shard ${shard}"
  for n in $nodes; do
    local state logsum target
    target=$(resolve_node_url "$n")
    state=$(curl -sS "${target}/raft/state" || true)
    logsum=$(curl -sS "${target}/raft/log/summary" || true)
    echo "  • ${target}"
    echo "    state: ${state}"
    echo "    log  : ${logsum}"
  done
}

check_all_shards(){
  local label="$1"
  for shard in $(shard_keys); do
    check_replication "$shard" "$label"
  done
}

curl_json(){ curl -sS -H "Content-Type: application/json" "$@"; }
wait_for_leader(){
  local shard="$1" tries=0
  while true; do
    local leader raw
    raw=$(curl --max-time 2 -sS "${COORD_URL}/leaders" || true)
    leader=$(echo "$raw" | python3 -c '
import sys, json
shard = sys.argv[1]
try:
    d = json.load(sys.stdin)
    info = d.get(shard)
    if isinstance(info, dict):
        print(info.get("leader",""))
    else:
        print("")
except Exception:
    print("")
' "$shard")
    if [[ -n "$leader" && "$leader" != "No disponible" ]]; then
      return 0
    fi
    tries=$((tries+1))
    if [[ $tries -ge 60 ]]; then
      log "❌ No se encontró líder para shard ${shard} tras ${tries} intentos. Último /leaders: ${raw}"
      return 1
    fi
    sleep 1
  done
}

wait_for_coord(){
  local tries=0
  until curl -sS "${COORD_URL}/health" >/dev/null 2>&1; do
    tries=$((tries+1))
    if [[ $tries -ge 40 ]]; then
      log "❌ Coordinador no respondió /health tras ${tries} intentos"
      return 1
    fi
    sleep 0.5
  done
}

get_shards_json(){
  # Construye shards a partir de /leaders (fallback si /cluster/status no está)
  # Formato esperado por SHARDS_CONFIG_JSON: {"shard_name": ["url1", "url2", ...], ...}
  local raw
  raw=$(curl --max-time 5 -sS "${COORD_URL}/leaders" || true)
  if [[ -z "$raw" ]]; then
    raw=$(curl --max-time 5 -sS "${COORD_URL}/cluster/status" || true)
  fi
  log "Debug HA - respuesta leaders/cluster: ${raw}"
  echo "$raw" | python3 -c '
import sys, json
try:
    data = json.load(sys.stdin)
    shards = {}
    if isinstance(data, dict):
        for shard, info in data.items():
            nodes = info.get("nodes") if isinstance(info, dict) else None
            if nodes:
                shards[shard] = nodes
    print(json.dumps(shards))
except Exception:
    print("")
'
}

# 1) Usuarios y auth
wait_for_coord || exit 1
wait_for_leader "users" || exit 1
wait_for_leader "eventos_a_m" || exit 1
wait_for_leader "eventos_n_z" || exit 1
RAND=$RANDOM
# Forzamos U1 en shard A-M (empieza con 'a') y U2 en shard N-Z (empieza con 'n')
U1="alice${RAND}"; U2="nina${RAND}"; PASS="pass123"
log "Registro/login de $U1 y $U2..."
REG1=$(curl_json -X POST "${COORD_URL}/auth/register" -d "{\"username\":\"$U1\",\"password\":\"$PASS\"}")
REG2=$(curl_json -X POST "${COORD_URL}/auth/register" -d "{\"username\":\"$U2\",\"password\":\"$PASS\"}")
log "Resp register U1: ${REG1}"
log "Resp register U2: ${REG2}"
RESP1=$(curl_json -X POST "${COORD_URL}/auth/login" -d "{\"username\":\"$U1\",\"password\":\"$PASS\"}")
RESP2=$(curl_json -X POST "${COORD_URL}/auth/login" -d "{\"username\":\"$U2\",\"password\":\"$PASS\"}")
TOK1=$(echo "$RESP1" | python3 -c '
import sys, json
try:
    data=json.load(sys.stdin)
    print(data.get("token",""))
except Exception:
    print("")
')
UID1=$(echo "$RESP1" | python3 -c '
import sys, json
try:
    data=json.load(sys.stdin)
    print(data.get("user_id",""))
except Exception:
    print("")
')
TOK2=$(echo "$RESP2" | python3 -c '
import sys, json
try:
    data=json.load(sys.stdin)
    print(data.get("token",""))
except Exception:
    print("")
')
UID2=$(echo "$RESP2" | python3 -c '
import sys, json
try:
    data=json.load(sys.stdin)
    print(data.get("user_id",""))
except Exception:
    print("")
')
log "Tokens: $TOK1 ($UID1), $TOK2 ($UID2)"
if [[ -z "$TOK1" || -z "$TOK2" ]]; then
  log "❌ Login devolvió tokens vacíos. RESP1=${RESP1} RESP2=${RESP2}"
  exit 1
fi

# 2) Grupos: crear, invitar, aceptar
log "Creando grupo..."
GRESP=$(curl_json -X POST "${COORD_URL}/groups?token=${TOK1}" -d '{"name":"g-ext","description":"demo","is_hierarchical":false}')
GID=$(echo "$GRESP"|parse group_id)
log "Invitando a $U2..."
curl_json -X POST "${COORD_URL}/groups/invite?group_id=${GID}&invited_user_id=${UID2}&token=${TOK1}" >/dev/null
log "Invitaciones para $U2:"
curl "${COORD_URL}/groups/invitations?token=${TOK2}" || true
INV_ID=$(curl -s "${COORD_URL}/groups/invitations?token=${TOK2}" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print(d[0]["id"] if isinstance(d, list) and d else "")
except Exception:
    print("")
')
if [[ -n "$INV_ID" ]]; then
  curl_json -X POST "${COORD_URL}/groups/invitations/respond?token=${TOK2}&invitation_id=${INV_ID}&response=accepted" >/dev/null
fi

# 3) Eventos: crear, invitación, aceptar, conflicto
START=$(date -d "+1 hour" +"%Y-%m-%d %H:%M:%S")
END=$(date -d "+2 hour" +"%Y-%m-%d %H:%M:%S")
log "Creando evento con invitación a $U2..."
ERESP=$(curl_json -X POST "${COORD_URL}/events?token=${TOK1}" -d "{\"title\":\"evt\",\"description\":\"demo\",\"start_time\":\"${START}\",\"end_time\":\"${END}\",\"participants_ids\":[${UID2}]}")
EID=$(echo "$ERESP"|parse event_id)
log "Evento id: ${EID}"
log "Invitaciones de eventos para $U2:"
curl "${COORD_URL}/events/invitations?token=${TOK2}" || true
if [[ -n "$EID" ]]; then
  curl_json -X POST "${COORD_URL}/events/invitations/respond?event_id=${EID}&accepted=true&token=${TOK2}" >/dev/null
fi

log "Creando evento conflictivo..."
CR=$(curl_json -X POST "${COORD_URL}/events?token=${TOK1}" -d "{\"title\":\"conflict\",\"description\":\"x\",\"start_time\":\"${START}\",\"end_time\":\"${END}\",\"participants_ids\":[${UID2}]}")
echo "$CR"
log "Conflictos $U2:"
curl "${COORD_URL}/events/conflicts?token=${TOK2}" || true

# 3.1) Chequeo de replicación/rol tras eventos iniciales
check_all_shards "Post-eventos iniciales"

# 4) Escalado: agregar nodos extra (todos los shards) requiere permisos Docker y overlay
if [[ -x "$ADD_NODE_SCRIPT" ]]; then
  KEEP_EXISTING=${KEEP_EXISTING:-1}
  DEFAULT_REPL=${DEFAULT_REPL:-2}
  log "Agregando nodos extra para todos los shards..."
  bash "$ADD_NODE_SCRIPT" EVENTOS_A_M raft_events_am_2 8802 http://raft_events_am_1:8801 http://coordinator:80 1 || true
  bash "$ADD_NODE_SCRIPT" EVENTOS_A_M raft_events_am_3 8803 http://raft_events_am_1:8801,http://raft_events_am_2:8802 http://coordinator:80 2 || true
  bash "$ADD_NODE_SCRIPT" EVENTOS_N_Z raft_events_nz_2 8805 http://raft_events_nz_1:8804 http://coordinator:80 1 || true
  bash "$ADD_NODE_SCRIPT" EVENTOS_N_Z raft_events_nz_3 8806 http://raft_events_nz_1:8804,http://raft_events_nz_2:8805 http://coordinator:80 2 || true
  bash "$ADD_NODE_SCRIPT" GRUPOS raft_groups_2 8808 http://raft_groups_1:8807 http://coordinator:80 1 || true
  bash "$ADD_NODE_SCRIPT" GRUPOS raft_groups_3 8809 http://raft_groups_1:8807,http://raft_groups_2:8808 http://coordinator:80 2 || true
  bash "$ADD_NODE_SCRIPT" USUARIOS raft_users_2 8811 http://raft_users_1:8810 http://coordinator:80 1 || true
  bash "$ADD_NODE_SCRIPT" USUARIOS raft_users_3 8812 http://raft_users_1:8810,http://raft_users_2:8811 http://coordinator:80 2 || true
  sleep 8
  log "Líderes tras escalado:"
  curl "${COORD_URL}/leaders" || true
  check_all_shards "Post-escalado"
fi

# 5) Failover extremo: tumbar dos nodos de EVENTOS_A_M y probar escrituras
log "Simulando caída de raft_events_am_1 y raft_events_am_2..."
docker stop raft_events_am_1 >/dev/null 2>&1 || true
docker stop raft_events_am_2 >/dev/null 2>&1 || true
sleep 5
log "Intentando crear evento con quorum reducido (espera fallo si no hay mayoría)..."
FAIL_RESP=$(curl -s -o /tmp/evt_fail.json -w "%{http_code}" -H "Content-Type: application/json" \
  -X POST "${COORD_URL}/events?token=${TOK1}" \
  -d "{\"title\":\"post-fail-2\",\"description\":\"x\",\"start_time\":\"${START}\",\"end_time\":\"${END}\"}")
log "HTTP post-fail-2: ${FAIL_RESP}, body=$(cat /tmp/evt_fail.json)"
check_all_shards "Tras caídas EVENTOS_A_M"

log "Agregando nodo de reemplazo raft_events_am_4..."
bash "$ADD_NODE_SCRIPT" EVENTOS_A_M raft_events_am_4 8813 http://raft_events_am_3:8803 http://coordinator:80 2 || true
sleep 6
log "Creando evento tras recuperar quorum..."
curl_json -X POST "${COORD_URL}/events?token=${TOK1}" -d "{\"title\":\"post-recover\",\"description\":\"x\",\"start_time\":\"${START}\",\"end_time\":\"${END}\"}" || true
log "Líderes finales:"
curl "${COORD_URL}/leaders" || true
check_all_shards "Post-recuperación"

# 6) Alta disponibilidad del coordinador (opcional, HA_COORD=1)
if [[ "${HA_COORD}" == "1" ]]; then
  log "== Iniciando prueba HA de coordinador =="
  log "Preparando coordinador de respaldo en puerto ${COORD_B_PORT}..."
  SHARDS_JSON=$(get_shards_json || true)
  log "Shards JSON usado para HA: ${SHARDS_JSON}"
  if [[ -z "$SHARDS_JSON" || "$SHARDS_JSON" == "{}" ]]; then
    log "⚠️  No se pudo obtener shards del coordinador principal (vacío); omitiendo prueba HA."
  else
    set +e  # no abortar el script por fallos en este bloque HA
    docker rm -f coordinator_b >/dev/null 2>&1 || true
    docker run -d --name coordinator_b --hostname coordinator_b --network agenda_net \
      -p ${COORD_B_PORT}:80 \
      -e SHARDS_CONFIG_JSON="$SHARDS_JSON" \
      agenda_backend uvicorn distributed.coordinator.router:app --host 0.0.0.0 --port 80 || log "⚠️ No se pudo lanzar coordinator_b (¿puerto ${COORD_B_PORT} ocupado?)."
    sleep 5
    log "coordinator_b lanzado?"; docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep coordinator_b || true
    log "Probando login vía coordinador de respaldo..."
    RESP_B=$(curl_json -X POST "${COORD_B_URL}/auth/login" -d "{\"username\":\"$U1\",\"password\":\"$PASS\"}")
    log "Resp backup login: ${RESP_B}"

    log "Deteniendo coordinador principal para probar failover (no se reusa el mismo)..."
    docker stop coordinator >/dev/null 2>&1 || true
    sleep 3
    log "Login mientras el principal está caído (usando backup)..."
    RESP_B2=$(curl_json -X POST "${COORD_B_URL}/auth/login" -d "{\"username\":\"$U1\",\"password\":\"$PASS\"}")
    log "Resp backup durante caída: ${RESP_B2}"

    log "Creando coordinador de reemplazo en puerto ${COORD_NEW_PORT}..."
    docker rm -f coordinator_new >/dev/null 2>&1 || true
    docker run -d --name coordinator_new --hostname coordinator_new --network agenda_net \
      -p ${COORD_NEW_PORT}:80 \
      -e SHARDS_CONFIG_JSON="$SHARDS_JSON" \
      agenda_backend uvicorn distributed.coordinator.router:app --host 0.0.0.0 --port 80 || log "⚠️ No se pudo lanzar coordinator_new (¿puerto ${COORD_NEW_PORT} ocupado?)."
    sleep 4
    log "coordinator_new lanzado?"; docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep coordinator_new || true
    log "Login a través del coordinador nuevo..."
    RESP_NEW=$(curl_json -X POST "${COORD_NEW_URL}/auth/login" -d "{\"username\":\"$U1\",\"password\":\"$PASS\"}")
    log "Resp coordinador nuevo: ${RESP_NEW}"

    log "Estado de líderes visto por coordinador nuevo:"
    curl "${COORD_NEW_URL}/leaders" || true
    log "== Fin de prueba HA de coordinador =="
    set -e
  fi
fi

log "🧪 Tests extremos terminados."
