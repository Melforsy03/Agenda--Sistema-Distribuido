#!/bin/bash
set -e

# ========================================================
# CONFIGURACIÓN MEJORADA PARA TOLERANCIA A FALLOS
# ========================================================
NETWORK_NAME="agenda_net"
DATA_VOLUME="agenda_data"
BACKEND_IMAGE="agenda_backend"
FRONTEND_IMAGE="agenda_frontend"

BACKEND_PORT_API=8766
BACKEND_PORT_WS=8767
FRONTEND_PORT=8501
COORDINATOR_PORT=8700

# Puertos para los 12 nodos RAFT (3 por shard × 4 shards)
RAFT_PORTS=(8801 8802 8803 8804 8805 8806 8807 8808 8809 8810 8811 8812)

# ========================================================
# FUNCIONES AUXILIARES
# ========================================================

function log() {
  echo -e "\033[1;36m$1\033[0m"
}

function error() {
  echo -e "\033[1;31m$1\033[0m"
}

function check_or_build_image() {
  local image=$1
  local dockerfile=$2

  if docker image inspect "$image" >/dev/null 2>&1; then
    log "✅ Imagen '$image' ya existe."
  else
    log "🐳 Construyendo imagen '$image'..."
    docker build -t "$image" -f "$dockerfile" .
  fi
}

function ensure_swarm() {
  if ! docker info | grep -q "Swarm: active"; then
    log "🌀 Inicializando Docker Swarm..."
    docker swarm init
  else
    log "✅ Docker Swarm ya está activo."
  fi
}

function ensure_network() {
  if ! docker network ls | grep -q "$NETWORK_NAME"; then
    log "🌐 Creando red overlay $NETWORK_NAME..."
    docker network create --driver overlay $NETWORK_NAME
  else
    log "✅ Red $NETWORK_NAME ya existe."
  fi
}

function ensure_volume() {
  if ! docker volume ls | grep -q "$DATA_VOLUME"; then
    log "💾 Creando volumen persistente $DATA_VOLUME..."
    docker volume create $DATA_VOLUME
  else
    log "✅ Volumen $DATA_VOLUME ya existe."
  fi
}

function create_raft_volumes() {
  for i in {1..12}; do
    vol_name="raft_data_$i"
    if ! docker volume ls | grep -q "$vol_name"; then
      docker volume create "$vol_name"
      log "💾 Volumen $vol_name creado."
    fi
  done
}

function get_shard_config() {
  local node_id=$1
  case $node_id in
    1|2|3)
      echo "EVENTOS_A_M"
      ;;
    4|5|6) 
      echo "EVENTOS_N_Z"
      ;;
    7|8|9)
      echo "GRUPOS"
      ;;
    10|11|12)
      echo "USUARIOS"
      ;;
    *)
      echo "DEFAULT"
      ;;
  esac
}

function get_peers_for_node() {
  local node_id=$1
  local shard=$(get_shard_config $node_id)
  
  case $shard in
    "EVENTOS_A_M")
      if [ $node_id -eq 1 ]; then echo "raft_node2,raft_node3"; fi
      if [ $node_id -eq 2 ]; then echo "raft_node1,raft_node3"; fi
      if [ $node_id -eq 3 ]; then echo "raft_node1,raft_node2"; fi
      ;;
    "EVENTOS_N_Z")
      if [ $node_id -eq 4 ]; then echo "raft_node5,raft_node6"; fi
      if [ $node_id -eq 5 ]; then echo "raft_node4,raft_node6"; fi
      if [ $node_id -eq 6 ]; then echo "raft_node4,raft_node5"; fi
      ;;
    "GRUPOS")
      if [ $node_id -eq 7 ]; then echo "raft_node8,raft_node9"; fi
      if [ $node_id -eq 8 ]; then echo "raft_node7,raft_node9"; fi
      if [ $node_id -eq 9 ]; then echo "raft_node7,raft_node8"; fi
      ;;
    "USUARIOS")
      if [ $node_id -eq 10 ]; then echo "raft_node11,raft_node12"; fi
      if [ $node_id -eq 11 ]; then echo "raft_node10,raft_node12"; fi
      if [ $node_id -eq 12 ]; then echo "raft_node10,raft_node11"; fi
      ;;
  esac
}

# ========================================================
# 1️⃣ Preparación inicial
# ========================================================
log "🚀 INICIANDO DESPLIEGUE CON TOLERANCIA A FALLOS"
log "================================================"

ensure_swarm
ensure_network
ensure_volume
create_raft_volumes

HOSTNAME=$(hostname)
IS_MANAGER=$(docker info 2>/dev/null | grep "Is Manager" | awk '{print $3}')

if [[ "$IS_MANAGER" == "true" ]]; then
  NODE_ROLE="manager"
else
  NODE_ROLE="worker"
fi

log "🖥️ Host detectado: $HOSTNAME ($NODE_ROLE)"

# ========================================================
# 2️⃣ Construcción condicional de imágenes
# ========================================================
check_or_build_image "$BACKEND_IMAGE" "Dockerfile.backend"
check_or_build_image "$FRONTEND_IMAGE" "Dockerfile.frontend"

# ========================================================
# 3️⃣ Despliegue dinámico según rol
# ========================================================
if [[ "$NODE_ROLE" == "manager" ]]; then
  log "🎯 Desplegando servicios principales en $HOSTNAME (manager)..."

  # === Backend principal ===
  log "🔧 Iniciando backend principal..."
  docker run -d \
    --name backend \
    --hostname backend \
    --network $NETWORK_NAME \
    -p ${BACKEND_PORT_API}:${BACKEND_PORT_API} \
    -p ${BACKEND_PORT_WS}:${BACKEND_PORT_WS} \
    -v $DATA_VOLUME:/app/data \
    -e DOCKER_ENV=true \
    -e PYTHONPATH=/app \
    -e WEBSOCKET_HOST=backend \
    -e WEBSOCKET_PORT=${BACKEND_PORT_WS} \
    $BACKEND_IMAGE \
    uvicorn backend.main:app --host 0.0.0.0 --port ${BACKEND_PORT_API}

  # === Coordinador RAFT ===
  log "🎯 Iniciando coordinador RAFT..."
  docker run -d \
    --name coordinator \
    --network $NETWORK_NAME \
    -p ${COORDINATOR_PORT}:${COORDINATOR_PORT} \
    -e PYTHONPATH=/app \
    $BACKEND_IMAGE \
    uvicorn distributed.coordinator.router:app --host 0.0.0.0 --port ${COORDINATOR_PORT}

  # === Nodos RAFT (12 nodos - 3 por cada shard) ===
  log "🏗️ Iniciando cluster RAFT con 12 nodos (3 por shard)..."
  
  for i in {1..12}; do
    port=${RAFT_PORTS[$((i-1))]}
    shard=$(get_shard_config $i)
    peers=$(get_peers_for_node $i)
    node_name="raft_node$i"
    
    log "🔄 Iniciando $node_name (Shard: $shard, Puerto: $port)"
    
    docker run -d \
      --name $node_name \
      --hostname $node_name \
      --network $NETWORK_NAME \
      -p ${port}:${port} \
      -v raft_data_${i}:/app/data \
      -e PYTHONPATH=/app \
      -e SHARD_NAME=$shard \
      -e NODE_ID=$node_name \
      -e PORT=$port \
      -e PEERS=$peers \
      $BACKEND_IMAGE \
      uvicorn distributed.nodes.raft_node:app --host 0.0.0.0 --port ${port}
    
    # Pequeña pausa entre nodos para evitar conflictos
    sleep 2
  done

  log "✅ Todos los nodos RAFT desplegados:"
  log "   - Shard EVENTOS A-M: raft_node1, raft_node2, raft_node3"
  log "   - Shard EVENTOS N-Z: raft_node4, raft_node5, raft_node6"  
  log "   - Shard GRUPOS:      raft_node7, raft_node8, raft_node9"
  log "   - Shard USUARIOS:    raft_node10, raft_node11, raft_node12"

else
  log "🎨 Desplegando frontend en $HOSTNAME (worker)..."
  
  # Esperar a que el backend esté disponible en el manager
  log "⏳ Esperando a que el backend esté disponible..."
  sleep 10

  docker run -d \
    --name frontend \
    --hostname frontend \
    --network $NETWORK_NAME \
    -p ${FRONTEND_PORT}:${FRONTEND_PORT} \
    -e PYTHONPATH=/app \
    -e API_URL=http://backend:${BACKEND_PORT_API} \
    -e WEBSOCKET_HOST=backend \
    -e WEBSOCKET_PORT=${BACKEND_PORT_WS} \
    $FRONTEND_IMAGE
fi

# ========================================================
# 4️⃣ Verificación y estado final
# ========================================================
log "📊 Esperando estabilización del sistema (15 segundos)..."
sleep 15

echo
log "📋 ESTADO ACTUAL DE CONTENEDORES:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo
log "🌍 ACCESOS DISPONIBLES:"
echo "  - API FastAPI:        http://localhost:${BACKEND_PORT_API}/docs"
echo "  - WebSocket:          ws://localhost:${BACKEND_PORT_WS}"
echo "  - Streamlit Front:    http://localhost:${FRONTEND_PORT}"
echo "  - Coordinator RAFT:   http://localhost:${COORDINATOR_PORT}"
echo "  - Estado líderes:     http://localhost:${COORDINATOR_PORT}/leaders"
echo "  - Estado cluster:     http://localhost:${COORDINATOR_PORT}/cluster/status"

echo
log "🔍 COMANDOS DE VERIFICACIÓN:"
echo "  Ver líderes:          curl http://localhost:${COORDINATOR_PORT}/leaders"
echo "  Estado cluster:       curl http://localhost:${COORDINATOR_PORT}/cluster/status"
echo "  Salud coordinador:    curl http://localhost:${COORDINATOR_PORT}/health"
echo "  Salud nodo RAFT:      curl http://localhost:8801/health"

echo
log "🧪 PRUEBA RÁPIDA:"
echo "  Crear evento:"
echo "  curl -X POST http://localhost:${COORDINATOR_PORT}/events \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"title\":\"Reunión\",\"description\":\"Test\",\"creator\":\"alice\",\"start_time\":\"2024-01-01 10:00\",\"end_time\":\"2024-01-01 11:00\"}'"

echo
log "✅ DESPLIEGUE COMPLETADO en $HOSTNAME ($NODE_ROLE)"
log "🛡️  SISTEMA CON TOLERANCIA A FALLOS ACTIVADA"