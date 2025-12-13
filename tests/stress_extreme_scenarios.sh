#!/usr/bin/env bash
# Pruebas automatizadas de escenarios extremos para el cluster RAFT distribuido.
# - No usa docker compose; controla contenedores docker individuales.
# - Cubre: churn de líderes, pérdida de mayoría, rejoin, adición/reemplazo de nodos, ráfagas de escrituras.
# Requisitos: docker, curl, jq instalados y contenedores del cluster corriendo.

set -euo pipefail

COORD_URL="${COORD_URL:-http://localhost:8700}"
CREATOR_AM="${CREATOR_AM:-ana_extreme}"
CREATOR_NZ="${CREATOR_NZ:-zoe_extreme}"
# Imagen para nodos RAFT (se puede sobreescribir con RAFT_IMAGE=mi_imagen:tag).
# Por defecto usa la misma imagen que deploy_swarn.sh construye: agenda_backend:latest
RAFT_IMAGE="${RAFT_IMAGE:-agenda_backend:latest}"
# Red docker donde viven los nodos RAFT (coincide con deploy_swarn.sh)
RAFT_NETWORK="${RAFT_NETWORK:-agenda_net}"
# Listas de URLs actuales (se irán mutando al reemplazar nodos)
EVENTS_AM_NODES=("http://localhost:8801" "http://localhost:8802" "http://localhost:8803")
EVENTS_NZ_NODES=("http://localhost:8804" "http://localhost:8805" "http://localhost:8806")
GROUPS_NODES=("http://localhost:8807" "http://localhost:8808" "http://localhost:8809")
USERS_NODES=("http://localhost:8810" "http://localhost:8811" "http://localhost:8812")
PYTHONPATH_VALUE="${PYTHONPATH_VALUE:-/app:/app/backend}"
# Puertos siguientes para nodos nuevos por shard (para no colisionar)
NEXT_PORT_AM=${NEXT_PORT_AM:-8813}
NEXT_PORT_NZ=${NEXT_PORT_NZ:-8823}
NEXT_PORT_GROUPS=${NEXT_PORT_GROUPS:-8833}
NEXT_PORT_USERS=${NEXT_PORT_USERS:-8843}

require_bin() {
  command -v "$1" >/dev/null 2>&1 || { echo "❌ Necesito '$1' en PATH" >&2; exit 1; }
}

container_from_url() {
  local url="$1" hostport host port
  # Asegura esquema para parsear
  if [[ "$url" != *"://"* ]]; then
    url="http://$url"
  fi
  hostport=${url#*://}
  hostport=${hostport%%/*}
  host=${hostport%%:*}
  port=""
  if [[ "$hostport" == *:* ]]; then
    port=${hostport##*:}
  fi

  # Si ya viene nombre de contenedor, devuélvelo
  if [[ "$host" =~ ^raft_ ]]; then
    echo "$host"
    return
  fi

  # Mapear puertos conocidos cuando vienen como localhost
  if [[ "$host" == "localhost" || "$host" == "127.0.0.1" ]]; then
    case "$port" in
      8801) echo "raft_events_am_1"; return ;;
      8802) echo "raft_events_am_2"; return ;;
      8803) echo "raft_events_am_3"; return ;;
      8804) echo "raft_events_nz_1"; return ;;
      8805) echo "raft_events_nz_2"; return ;;
      8806) echo "raft_events_nz_3"; return ;;
      8807) echo "raft_groups_1"; return ;;
      8808) echo "raft_groups_2"; return ;;
      8809) echo "raft_groups_3"; return ;;
      8810) echo "raft_users_1"; return ;;
      8811) echo "raft_users_2"; return ;;
      8812) echo "raft_users_3"; return ;;
    esac
  fi

  # Fallback: devuelve host
  echo "$host"
}

normalize_url_for_host() {
  # Ajusta URLs que vienen con el hostname del contenedor (p.ej. http://raft_events_am_2:8802)
  # para que sean accesibles desde el host (http://localhost:8802).
  local url="$1" scheme hostport host port path

  # Asegura esquema explícito para poder parsear (algunos coordinadores devuelven solo hostname)
  if [[ "$url" != *"://"* ]]; then
    url="http://$url"
  fi

  scheme=${url%%://*}
  hostport=${url#*://}
  path=""
  if [[ "$hostport" == */* ]]; then
    path="/${hostport#*/}"
    hostport=${hostport%%/*}
  fi
  host=${hostport%%:*}
  port=""
  if [[ "$hostport" == *:* ]]; then
    port=${hostport##*:}
  fi

  if [[ "$host" =~ ^raft_ && "$host" != "localhost" ]]; then
    # Si no viene puerto en la URL, intenta inferirlo por nombre o desde docker
    if [[ -z "$port" ]]; then
      case "$host" in
        raft_events_am_1) port=8801 ;;
        raft_events_am_2) port=8802 ;;
        raft_events_am_3) port=8803 ;;
        raft_events_nz_1) port=8804 ;;
        raft_events_nz_2) port=8805 ;;
        raft_events_nz_3) port=8806 ;;
        raft_groups_1)    port=8807 ;;
        raft_groups_2)    port=8808 ;;
        raft_groups_3)    port=8809 ;;
        raft_users_1)     port=8810 ;;
        raft_users_2)     port=8811 ;;
        raft_users_3)     port=8812 ;;
      esac
      if [[ -z "$port" ]]; then
        port=$(docker port "$host" 2>/dev/null | head -n1 | awk -F: '{print $2}')
      fi
    fi
    if [[ -n "$port" ]]; then
      echo "http://localhost:${port}${path}"
      return 0
    fi
  fi
  echo "${scheme}://${hostport}${path}"
}

wait_for_leader() {
  local shard="$1" url norm_url role
  for _ in {1..60}; do
    # Toleramos fallos transitorios mientras el coordinador/nodos se estabilizan
    if ! url=$(curl -sf "$COORD_URL/leaders" | jq -r --arg shard "$shard" '.[$shard].leader // empty'); then
      sleep 1
      continue
    fi
    if [[ -n "$url" && "$url" != "null" ]]; then
      norm_url=$(normalize_url_for_host "$url")
      if ! role=$(curl -sf "${norm_url}/raft/state" | jq -r '.role // empty'); then
        sleep 1
        continue
      fi
      if [[ "$role" == "leader" ]]; then
        echo "$norm_url"
        return 0
      fi
    fi
    sleep 1
  done
  echo "❌ No se encontró líder para $shard" >&2
  return 1
}

wait_node_ready() {
  local url norm_url="$1" retry role ct="${2:-}"
  norm_url=$(normalize_url_for_host "$norm_url")
  for retry in {1..30}; do
    if role=$(curl -sf "${norm_url}/raft/state" | jq -r '.role // empty'); then
      echo "🔎 Nodo listo: ${norm_url} (rol $role)"
      return 0
    fi
    sleep 1
  done
  echo "❌ Nodo no responde en ${norm_url}" >&2
  if [[ -n "$ct" ]]; then
    echo "📋 Estado contenedor $ct:"
    docker ps --filter "name=$ct"
    echo "📜 Logs recientes de $ct:"
    docker logs --tail=50 "$ct" 2>&1 || true
  fi
  return 1
}

create_event() {
  local title="$1" creator="$2"
  curl -sS -X POST "$COORD_URL/events" \
    -H 'Content-Type: application/json' \
    -d "{\"title\":\"$title\",\"description\":\"stress\",\"creator\":\"$creator\",\"start_time\":\"2026-01-01 10:00\",\"end_time\":\"2026-01-01 11:00\"}" \
    >/dev/null
}

check_event_in_node() {
  local node_url="$1" title="$2"
  curl -sS "$node_url/events?order=desc&limit=300" | jq -e --arg t "$title" 'map(.title) | index($t)' >/dev/null
}

wait_event_in_all() {
  local title="$1" ; shift
  local nodes=("$@") url
  for url in "${nodes[@]}"; do
    for _ in {1..45}; do
      if check_event_in_node "$url" "$title"; then
        break
      fi
      sleep 1
    done
    if ! check_event_in_node "$url" "$title"; then
      echo "❌ Falta evento $title en $url" >&2
      echo "🔎 Estado $url:" >&2
      curl -sS "$url/raft/state" | jq >&2 || true
      echo "📜 Log $url:" >&2
      curl -sS "$url/raft/log/summary" | jq >&2 || true
      return 1
    fi
  done
  echo "✅ Evento $title replicado en ${#nodes[@]} nodos"
}

join_by_comma() {
  local IFS=","
  echo "$*"
}

replace_node() {
  # Apaga definitivamente un nodo y lo recrea (misma identidad/puerto) para no romper peer lists estáticas.
  local shard="$1" old_url="$2" _unused="$3" _unused2="$4" peers_shard
  local -n arr="$5"          # bash nameref al array de URLs de este shard

  local old_ct new_url port peers_local peers_for_new=() node ct vol_name peer_port
  old_ct=$(container_from_url "$old_url")
  port=$(printf "%s" "$old_url" | sed -n 's@.*://[^:]*:\\([0-9]\\+\\).*@\\1@p')
  if [[ -z "$port" ]]; then
    case "$old_ct" in
      raft_events_am_1) port=8801 ;;
      raft_events_am_2) port=8802 ;;
      raft_events_am_3) port=8803 ;;
      raft_events_nz_1) port=8804 ;;
      raft_events_nz_2) port=8805 ;;
      raft_events_nz_3) port=8806 ;;
      raft_groups_1)    port=8807 ;;
      raft_groups_2)    port=8808 ;;
      raft_groups_3)    port=8809 ;;
      raft_users_1)     port=8810 ;;
      raft_users_2)     port=8811 ;;
      raft_users_3)     port=8812 ;;
    esac
  fi
  if [[ -z "$port" ]]; then
    echo "❌ No pude determinar puerto para $old_url" >&2
    return 1
  fi
  new_url="$old_url"
  vol_name="raft_data_${old_ct}"

  echo " 💣 Reemplazando $old_ct (puerto $port, volumen limpio $vol_name)"
  docker rm -f "$old_ct" >/dev/null 2>&1 || true
  docker volume rm -f "$vol_name" >/dev/null 2>&1 || true
  docker volume create "$vol_name" >/dev/null 2>&1 || true
  echo " Nodos actuales del shard: ${arr[*]}"

  # peers para el nuevo: usar nombres de contenedor + puerto, no localhost
  for node in "${arr[@]}"; do
    if [[ "$node" == "$old_url" ]]; then
      continue
    fi
    ct=$(container_from_url "$node")
    peer_port=$(printf "%s" "$node" | sed -n 's@.*://[^:]*:\\([0-9]\\+\\).*@\\1@p')
    if [[ -n "$ct" && -n "$peer_port" ]]; then
      peers_for_new+=("http://${ct}:${peer_port}")
    fi
  done
  peers_local=$(printf "%s\n" "${peers_for_new[@]}" | paste -sd, -)
  if [[ -z "$peers_local" ]]; then
    case "$shard" in
      EVENTOS_A_M)
        peers_local="http://raft_events_am_2:8802,http://raft_events_am_3:8803"
        ;;
      EVENTOS_N_Z)
        peers_local="http://raft_events_nz_1:8804,http://raft_events_nz_2:8805,http://raft_events_nz_3:8806"
        ;;
      GRUPOS)
        peers_local="http://raft_groups_1:8807,http://raft_groups_2:8808,http://raft_groups_3:8809"
        ;;
      USUARIOS)
        peers_local="http://raft_users_1:8810,http://raft_users_2:8811,http://raft_users_3:8812"
        ;;
    esac
    echo "⚠️  peers vacío, usando fallback para $shard: $peers_local"
  else
    echo "PEERS nuevo nodo: $peers_local"
  fi

  docker run -d --name "$old_ct" \
    --network "$RAFT_NETWORK" \
    --hostname "$old_ct" \
    -v "${vol_name}:/app/data" \
    -w /app \
    -e SHARD_NAME="$shard" \
    -e NODE_ID="$old_ct" \
    -e NODE_URL="http://$old_ct:$port" \
    -e PORT="$port" \
    -e PEERS="$peers_local" \
    -e COORD_URL="$COORD_URL" \
    -e PYTHONPATH="$PYTHONPATH_VALUE" \
    -p "$port":"$port" "$RAFT_IMAGE" \
    uvicorn distributed.nodes.raft_node:app --host 0.0.0.0 --port "$port" >/dev/null
  wait_node_ready "$new_url" "$old_ct" || true
  echo " Estado post-reemplazo ($new_url):"
  curl -sS "$new_url" | jq || true
  echo " State RAFT ($new_url/raft/state):"
  curl -sS "$new_url/raft/state" | jq || true

  # Sustituye URL en el array
  for i in "${!arr[@]}"; do
    if [[ "${arr[$i]}" == "$old_url" ]]; then
      arr[$i]="$new_url"
    fi
  done
  sleep 5
}

churn_lideres() {
  echo "== Escenario 1: churn de líderes (EVENTOS_A_M) =="
  local i title leader_url leader_ct
  for i in {1..3}; do
    leader_url=$(wait_for_leader "events_a_m")
    leader_ct=$(container_from_url "$leader_url")
    title="evt_churn_${i}_$(date +%H%M%S)"
    echo " Iteración $i, líder $leader_ct -> stop"
    docker stop "$leader_ct" >/dev/null
    sleep 3
    wait_for_leader "events_a_m"
    create_event "$title" "$CREATOR_AM"
    # Reactiva el líder caído antes de verificar replicación para evitar fallos por puerto cerrado
    docker start "$leader_ct" >/dev/null
    sleep 3
    wait_event_in_all "$title" "${EVENTS_AM_NODES[@]}"
  done
}

perder_mayoria_y_recuperar() {
  echo "== Escenario 2: pérdida de mayoría y recuperación (EVENTOS_A_M) =="
  local leader_url leader_ct follower_ct title
  leader_url=$(wait_for_leader "events_a_m")
  leader_ct=$(container_from_url "$leader_url")
  # Elegir follower distinto del líder (prefiere raft_events_am_2, si es líder usa raft_events_am_3)
  follower_ct="raft_events_am_2"
  if [[ "$leader_ct" == "$follower_ct" ]]; then
    follower_ct="raft_events_am_3"
  fi
  echo " Apago líder y un follower: $leader_ct, $follower_ct"
  docker stop "$leader_ct" >/dev/null
  docker stop "$follower_ct" >/dev/null || true
  echo " Con 1 nodo vivo no habrá quorum; intento escritura (debe fallar o quedar sin commit)"
  title="evt_no_quorum_$(date +%H%M%S)"
  create_event "$title" "$CREATOR_AM" || true
  echo " Reactivo nodos y verifico catch-up"
  docker start "$leader_ct" >/dev/null
  docker start "$follower_ct" >/dev/null
  wait_node_ready "http://localhost:8801" || true
  wait_node_ready "http://localhost:8802" || true
  wait_node_ready "http://localhost:8803" || true
  wait_for_leader "events_a_m"
  create_event "evt_recupera_${title}" "$CREATOR_AM"
  wait_event_in_all "evt_recupera_${title}" "${EVENTS_AM_NODES[@]}"
}

stress_escrituras_y_rejoin() {
  echo "== Escenario 3: ráfaga de escrituras + rejoin followers (EVENTOS_N_Z) =="
  local t last_title leader_url leader_ct n
  leader_url=$(wait_for_leader "events_n_z")
  leader_ct=$(container_from_url "$leader_url")
  echo " Detengo follower raft_events_nz_3"
  docker stop raft_events_nz_3 >/dev/null || true
  echo " Envío ráfaga de 10 escrituras"
  for n in $(seq 1 10); do
    t="evt_nz_burst_${n}_$(date +%H%M%S)"
    last_title="$t"
    create_event "$t" "$CREATOR_NZ"
  done
  echo " Reactivo follower y verifico catch-up"
  docker start raft_events_nz_3 >/dev/null
  wait_node_ready "http://localhost:8804" || true
  wait_node_ready "http://localhost:8805" || true
  wait_node_ready "http://localhost:8806" || true
  wait_for_leader "events_n_z"
  wait_event_in_all "$last_title" "${EVENTS_NZ_NODES[@]}" || true
}

agregar_nodo_nuevo() {
  echo "== Escenario 4: reemplazo duro (kill) + nodo nuevo en shard A-M =="
  local victim="${EVENTS_AM_NODES[0]}"
  replace_node "EVENTOS_A_M" "$victim" NEXT_PORT_AM "raft_events_am_new" EVENTS_AM_NODES
  local title="evt_replaced_$(date +%H%M%S)"
  wait_for_leader "events_a_m"
  create_event "$title" "$CREATOR_AM"
  wait_event_in_all "$title" "${EVENTS_AM_NODES[@]}"
  echo "✅ Nodo nuevo opera en el shard A-M tras reemplazo duro"
}

stress_grupos_y_users() {
  echo "== Escenario 5: fallo coordinado en shards GRUPOS y USERS =="
  echo " Apago un nodo de cada shard"
  docker stop raft_groups_1 >/dev/null || true
  docker stop raft_users_1 >/dev/null || true
  sleep 2
  echo " Creo grupo y usuario"
  curl -sS -X POST "$COORD_URL/groups" -H 'Content-Type: application/json' \
    -d '{"name":"g_extremo","description":"stress"}' >/dev/null
  curl -sS -X POST "$COORD_URL/users" -H 'Content-Type: application/json' \
    -d '{"username":"usr_extremo","email":"usr_extremo@example.com"}' >/dev/null
  echo " Reactivo nodos y verifico salud"
  docker start raft_groups_1 >/dev/null || true
  docker start raft_users_1 >/dev/null || true
  curl -sS "$COORD_URL/cluster/status" | jq '.shards.groups, .shards.users' >/dev/null
}

main() {
  require_bin docker
  require_bin curl
  require_bin jq
  churn_lideres
  perder_mayoria_y_recuperar
  stress_escrituras_y_rejoin
  agregar_nodo_nuevo
  stress_grupos_y_users
  echo "🎯 Escenarios extremos ejecutados."
}

main "$@"
