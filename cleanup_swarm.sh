#!/bin/bash
set -e

NETWORK_NAME="agenda_net"
DATA_VOLUME="agenda_data"

echo "🧹 Limpiando entorno de despliegue (contenedores, red y volumen persistente)..."

# 1️⃣ Eliminar contenedores activos
containers=$(docker ps -aq --filter "name=backend" \
                         --filter "name=frontend" \
                         --filter "name=coordinator" \
                         --filter "name=raft_node")

if [ -n "$containers" ]; then
  echo "🗑️  Eliminando contenedores existentes..."
  docker rm -f $containers >/dev/null 2>&1 || true
else
  echo "✅ No hay contenedores activos."
fi

# 2️⃣ Eliminar red overlay (si existe)
if docker network ls | grep -q "$NETWORK_NAME"; then
  echo "🌐 Eliminando red overlay $NETWORK_NAME..."
  docker network rm $NETWORK_NAME >/dev/null 2>&1 || true
fi

# 3️⃣ Eliminar volumen persistente (opcional)
if docker volume ls | grep -q "$DATA_VOLUME"; then
  echo "💾 Eliminando volumen persistente $DATA_VOLUME..."
  docker volume rm $DATA_VOLUME >/dev/null 2>&1 || true
fi

# 4️⃣ Mostrar resumen
echo
docker system df
echo
echo "✅ Limpieza completada. Entorno listo para nuevo despliegue."
