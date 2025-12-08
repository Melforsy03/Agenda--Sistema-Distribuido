#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "-> Construyendo imágenes y levantando servicios con docker compose..."
# build and start
docker compose build --pull --no-cache
docker compose up -d

# wait for backend openapi to be available
BACKEND_URL="http://localhost:8766/openapi.json"
MAX_WAIT=60
count=0

echo "-> Esperando a que el backend responda en $BACKEND_URL (máx ${MAX_WAIT}s)..."
until curl -sSf "$BACKEND_URL" >/dev/null 2>&1 || [ $count -ge $MAX_WAIT ]; do
  sleep 1
  count=$((count+1))
  printf "."
done

if [ $count -ge $MAX_WAIT ]; then
  echo
  echo "¡Atención!: backend no respondió dentro del tiempo esperado. Revisa logs: docker compose logs backend --tail=200"
  exit 1
fi

echo
echo "✅ Servicios levantados y backend disponible. Estado de contenedores:"
docker compose ps

echo
cat <<EOF
Siguientes pasos sugeridos:
 - Ver logs: docker compose logs -f backend
 - Abrir frontend: http://localhost:8501
 - OpenAPI/backend: http://localhost:8766/docs
 - Coordenador RAFT: http://localhost:8700 (si está presente)
 - Probar endpoints (ejemplo):
     curl -v http://localhost:8766/openapi.json
 - Para simular fallo de un nodo RAFT (ej. raft1):
     docker compose stop raft1
   Observa logs de los demás nodos y del coordinador:
     docker compose logs -f raft2 raft3 raft4 coordinator
   Para reiniciar: docker compose start raft1
EOF

exit 0
