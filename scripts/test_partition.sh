#!/usr/bin/env bash
set -euo pipefail

# Simula una partición de red: desconecta nodos de un shard, verifica líderes
# y prueba que el sistema sigue operando con menos instancias.
#
# Variables:
#   COORD_URL       (default http://localhost:8700)
#   NET             (default agenda_net)
#   PARTITION_NODES (lista explícita de contenedores a aislar; si vale "AUTO_MASS" se seleccionan todos los raft_* salvo los _1)

COORD_URL=${COORD_URL:-http://localhost:8700}
NET=${NET:-agenda_net}
# Por defecto, aislar muchos nodos dejando vivos los seeds *_1 de cada shard
PARTITION_NODES=${PARTITION_NODES:-"AUTO_MASS"}

ts(){ date +"%Y-%m-%d %H:%M:%S"; }
# Registrar en stderr para no contaminar capturas de stdout
log(){ echo "[$(ts)] $*" >&2; }

parse_json(){
  local key="$1"
  python3 -c '
import sys,json
key=sys.argv[1]
try:
    d=json.load(sys.stdin)
    if isinstance(d, dict):
        print(d.get(key,""))
    else:
        print("")
except Exception:
    print("")
' "$key"
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

wait_for_leader(){
  local shard="$1" tries=0
  while true; do
    local raw leader
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

show_leaders(){
  log "Líderes actuales:"
  curl -sS "${COORD_URL}/leaders" || true
}

disconnect_nodes(){
  for n in $PARTITION_NODES; do
    log "🔌 Desconectando ${n} de ${NET}..."
    docker network disconnect "$NET" "$n" >/dev/null 2>&1 || true
  done
}

reconnect_nodes(){
  for n in $PARTITION_NODES; do
    log "🔗 Reconectando ${n} a ${NET}..."
    docker network connect "$NET" "$n" >/dev/null 2>&1 || true
  done
}

auto_partition_nodes(){
  # Selecciona todos los raft_* en ejecución y deja al menos 1 por shard (el de menor sufijo)
  local shard num
  declare -A keep
  declare -A keepnum
  mapfile -t names < <(docker ps --format '{{.Names}}' | grep '^raft_' | grep -vE 'coordinator|frontend|backend')
  [[ ${#names[@]} -eq 0 ]] && return
  for n in "${names[@]}"; do
    shard="${n%_[0-9]*}"
    num="${n##*_}"
    if [[ -z "${keep[$shard]-}" || "${num}" -lt "${keepnum[$shard]:-9999}" ]]; then
        keep[$shard]="$n"
        keepnum[$shard]="$num"
    fi
  done
  # El resultado de partición excluye los "keep" (uno por shard) y devuelve el resto
  for n in "${names[@]}"; do
    shard="${n%_[0-9]*}"
    if [[ "${keep[$shard]}" != "$n" ]]; then
      printf "%s " "$n"
    fi
  done
}

create_user_and_login(){
  local user="$1" pass="$2"
  local reg resp tok uid
  reg=$(curl -sS -H "Content-Type: application/json" -X POST "${COORD_URL}/auth/register" -d "{\"username\":\"$user\",\"password\":\"$pass\"}")
  log "Resp register ${user}: ${reg}"
  resp=$(curl -sS -H "Content-Type: application/json" -X POST "${COORD_URL}/auth/login" -d "{\"username\":\"$user\",\"password\":\"$pass\"}")
  tok=$(echo "$resp" | parse_json token)
  uid=$(echo "$resp" | parse_json user_id)
  echo "${tok}:${uid}"
}

create_event(){
  local tok="$1" title="$2" start="$3" end="$4"
  curl -sS -H "Content-Type: application/json" \
    -X POST "${COORD_URL}/events?token=${tok}" \
    -d "{\"title\":\"${title}\",\"description\":\"demo\",\"start_time\":\"${start}\",\"end_time\":\"${end}\"}"
}

main(){
  wait_for_coord || exit 1
  wait_for_leader "users" || exit 1
  wait_for_leader "eventos_a_m" || exit 1
  show_leaders

  local RAND=$RANDOM
  local U1="alice${RAND}"
  local PASS="pass123"
  local TOK_UID
  TOK_UID=$(create_user_and_login "$U1" "$PASS")
  local TOK=${TOK_UID%%:*}
  local START END
  if [[ -z "$TOK" ]]; then
    log "❌ Login falló, token vacío."
    exit 1
  fi
  START=$(date -d "+1 hour" +"%Y-%m-%d %H:%M:%S")
  END=$(date -d "+2 hour" +"%Y-%m-%d %H:%M:%S")

  log "Creando evento base..."
  create_event "$TOK" "evt-base" "$START" "$END"

  if [[ "$PARTITION_NODES" == "AUTO_MASS" ]]; then
    PARTITION_NODES="$(auto_partition_nodes)"
  fi
  log "== Particionando nodos: ${PARTITION_NODES}"
  disconnect_nodes
  sleep 3
  # Espera que se re-elige un líder con los nodos restantes
  if ! wait_for_leader "eventos_a_m"; then
    log "⚠️  No se encontró líder en eventos_a_m tras partición; se sigue intentando operar de todas formas."
  fi
  show_leaders

  log "Creando evento durante partición (puede degradarse)..."
  create_event "$TOK" "evt-part" "$START" "$END"

  log "== Restaurando red =="
  reconnect_nodes
  sleep 5
  show_leaders

  log "Creando evento tras reconexión..."
  create_event "$TOK" "evt-recover" "$START" "$END"

  log "✅ Prueba de partición finalizada."
}

main "$@"
