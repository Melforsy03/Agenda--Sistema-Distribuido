#!/bin/bash
set -e

# ========================================================
# CONFIGURACIÓN BÁSICA
# ========================================================
NETWORK_NAME="agenda_net"
DATA_VOLUME="agenda_data"
BACKEND_IMAGE="agenda_backend"
FRONTEND_IMAGE="agenda_frontend"

BACKEND_PORT_API=8766
BACKEND_PORT_WS=8767
FRONTEND_PORT=8501
COORDINATOR_PORT=8700

# ========================================================
# FUNCIONES AUXILIARES
# ========================================================

function log() {
  echo -e "\033[1;36m$1\033[0m"
}

function check_or_build_image() {
  local image=$1
  local dockerfile=$2

  if docker image inspect "$image" >/dev/null 2>&1; then
    log "✅ Imagen '$image' ya existe. No se reconstruirá."
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

# ========================================================
# 1️⃣ Preparación inicial
# ========================================================
ensure_swarm
ensure_network
ensure_volume

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
  log "🚀 Desplegando servicios principales (backend, coordinator, RAFT) en $HOSTNAME..."

  # === Backend principal ===
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
  docker run -d \
    --name coordinator \
    --network $NETWORK_NAME \
    -p ${COORDINATOR_PORT}:${COORDINATOR_PORT} \
    -e PYTHONPATH=/app \
    $BACKEND_IMAGE \
    uvicorn distributed.coordinator.router:app --host 0.0.0.0 --port ${COORDINATOR_PORT}

  # === Nodos RAFT (4 shards simulados) ===
  for i in 1 2 3 4; do
    port=$((8800 + i))
    log "➡️ Iniciando nodo RAFT ${i} en puerto ${port}..."
    docker run -d \
      --name raft_node${i} \
      --network $NETWORK_NAME \
      -p ${port}:${port} \
      -e PYTHONPATH=/app \
      $BACKEND_IMAGE \
      uvicorn distributed.nodes.node${i}_*/raft_node:app --host 0.0.0.0 --port ${port}
  done

else
  log "🟩 Desplegando frontend en $HOSTNAME (worker)..."

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
# 4️⃣ Mostrar estado
# ========================================================
echo
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo
log "🌍 Accesos:"
echo "  - API FastAPI:     http://localhost:${BACKEND_PORT_API}/docs"
echo "  - WebSocket:       ws://localhost:${BACKEND_PORT_WS}"
echo "  - Streamlit Front: http://localhost:${FRONTEND_PORT}"
echo "  - Coordinator:     http://localhost:${COORDINATOR_PORT}/leaders"
echo
log "✅ Despliegue completado dinámicamente en $HOSTNAME."

