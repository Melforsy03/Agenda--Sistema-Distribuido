#!/usr/bin/env bash
set -euo pipefail

# Test extremo básico de la aplicación distribuida contra el coordinador.
# Requisitos: curl, python3, cluster levantado (coordinator en COORD_URL).
#
# Ejecuta:
#   scripts/test_distributed.sh
#
# Variables opcionales:
#   COORD_URL (default http://localhost:8700)

COORD_URL=${COORD_URL:-http://localhost:8700}

ts() { date +"%Y-%m-%d %H:%M:%S"; }
parse_json() { python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('$1',''))"; }

curl_json() {
  local method=$1; shift
  local url=$1; shift
  curl -sS -X "$method" -H "Content-Type: application/json" "$url" "$@"
}

log() { echo "[$(ts)] $*"; }

RAND=$RANDOM
U1="alice${RAND}"
U2="bob${RAND}"
PASS="pass123"

log "Registrando usuarios $U1 y $U2..."
REG1=$(curl_json POST "${COORD_URL}/auth/register" -d "{\"username\":\"$U1\",\"password\":\"$PASS\"}")
REG2=$(curl_json POST "${COORD_URL}/auth/register" -d "{\"username\":\"$U2\",\"password\":\"$PASS\"}")
log "Resp register u1: $REG1"
log "Resp register u2: $REG2"

log "Login de usuarios..."
RESP1=$(curl_json POST "${COORD_URL}/auth/login" -d "{\"username\":\"$U1\",\"password\":\"$PASS\"}")
RESP2=$(curl_json POST "${COORD_URL}/auth/login" -d "{\"username\":\"$U2\",\"password\":\"$PASS\"}")
TOK1=$(echo "$RESP1" | parse_json token)
TOK2=$(echo "$RESP2" | parse_json token)
UID1=$(echo "$RESP1" | parse_json user_id)
UID2=$(echo "$RESP2" | parse_json user_id)
if [[ -z "$TOK1" || -z "$TOK2" ]]; then
  log "❌ Falló login. RESP1=$RESP1 RESP2=$RESP2 (revisa COORD_URL=$COORD_URL y despliegue)"
  exit 1
fi
log "Tokens obtenidos: $TOK1 (u1:$UID1), $TOK2 (u2:$UID2)"

log "Creando grupo..."
GROUP_RESP=$(curl_json POST "${COORD_URL}/groups?token=${TOK1}" -d '{"name":"g-test","description":"demo","is_hierarchical":false}')
GROUP_ID=$(echo "$GROUP_RESP" | parse_json group_id)
if [[ -z "$GROUP_ID" || "$GROUP_ID" == "None" ]]; then GROUP_ID=1; fi
log "Grupo id: $GROUP_ID"

log "Invitando a $U2 al grupo..."
curl_json POST "${COORD_URL}/groups/invite?group_id=${GROUP_ID}&invited_user_id=${UID2}&token=${TOK1}" >/dev/null

log "Listando invitaciones de grupo para $U2..."
INV_LIST=$(curl_json GET "${COORD_URL}/groups/invitations?token=${TOK2}")
echo "$INV_LIST"

log "Respondiendo invitación (aceptar)..."
INV_ID=$(echo "$INV_LIST" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data[0]['id'] if isinstance(data,list) and data else '')")
if [[ -n "$INV_ID" ]]; then
  curl_json POST "${COORD_URL}/groups/invitations/respond?token=${TOK2}&invitation_id=${INV_ID}&response=accepted" >/dev/null
else
  log "⚠️ No se encontró invitación de grupo para aceptar"
fi

log "Creando evento con invitación a $U2..."
START=$(date -d "+1 hour" +"%Y-%m-%d %H:%M:%S")
END=$(date -d "+2 hour" +"%Y-%m-%d %H:%M:%S")
EVENT_RESP=$(curl_json POST "${COORD_URL}/events?token=${TOK1}" -d "{\"title\":\"e-test\",\"description\":\"demo\",\"start_time\":\"${START}\",\"end_time\":\"${END}\",\"participants_ids\":[${UID2}]}")
EVENT_ID=$(echo "$EVENT_RESP" | parse_json event_id)
log "Evento id: $EVENT_ID"

log "Listando invitaciones de eventos para $U2..."
curl_json GET "${COORD_URL}/events/invitations?token=${TOK2}"

log "Respondiendo invitación de evento (aceptar)..."
if [[ -n "$EVENT_ID" ]]; then
  curl_json POST "${COORD_URL}/events/invitations/respond?event_id=${EVENT_ID}&accepted=true&token=${TOK2}" >/dev/null
fi

log "Listando eventos detallados para $U1..."
curl_json GET "${COORD_URL}/events/detailed?token=${TOK1}"

log "Creando evento con conflicto para $U2..."
CONFLICT_RESP=$(curl_json POST "${COORD_URL}/events?token=${TOK1}" -d "{\"title\":\"e-conflict\",\"description\":\"conflict\",\"start_time\":\"${START}\",\"end_time\":\"${END}\",\"participants_ids\":[${UID2}]}")
echo "$CONFLICT_RESP"

log "Conflictos registrados para $U2..."
curl_json GET "${COORD_URL}/events/conflicts?token=${TOK2}"

log "Test terminado."
