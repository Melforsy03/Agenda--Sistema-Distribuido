#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# Config
BACKEND_HOST="localhost"
BACKEND_API_PORT=8766
COORD_HOST="localhost"
COORD_PORT=8700

mkdir -p tmp

echo "1) Comprobando OpenAPI del backend..."
if ! curl -sS "http://${BACKEND_HOST}:${BACKEND_API_PORT}/openapi.json" >/dev/null; then
  echo "ERROR: backend no responde en http://${BACKEND_HOST}:${BACKEND_API_PORT}"
  exit 2
fi

echo "OK: backend responde."

echo
echo "2) Intentando crear usuario de prueba (ajusta payload según tu API)..."
# Ajusta la ruta/payload si tu API es distinta
CREATE_USER_URL="http://${BACKEND_HOST}:${BACKEND_API_PORT}/auth/register"
USER_PAYLOAD='{"username":"testuser_local","password":"TestPass123"}'

set +e
resp=$(curl -s -o /dev/stderr -w "%{http_code}" -X POST "$CREATE_USER_URL" -H 'Content-Type: application/json' -d "$USER_PAYLOAD")
rc=$?
set -e

if [ $rc -ne 0 ]; then
  echo "Aviso: fallo al intentar crear usuario (curl error). Revisa backend logs."
else
  echo "Respuesta (HTTP code): $resp"
fi

echo
echo "3) Intentando crear evento de prueba vía coordinador (si corresponde)..."
CREATE_EVENT_URL="http://${COORD_HOST}:${COORD_PORT}/events"
EVENT_PAYLOAD='{"title":"Prueba","description":"Evento de prueba","creator":"testuser_local","start_time":"2025-12-03 10:00","end_time":"2025-12-03 11:00"}'

set +e
resp2=$(curl -s -o /dev/stderr -w "%{http_code}" -X POST "$CREATE_EVENT_URL" -H 'Content-Type: application/json' -d "$EVENT_PAYLOAD")
rc2=$?
set -e

if [ $rc2 -ne 0 ]; then
  echo "Aviso: fallo al crear evento (curl error) — puede que el endpoint no exista en el coordinador."
else
  echo "Respuesta (HTTP code): $resp2"
fi

echo
echo "4) Extrayendo bases de datos de nodos RAFT (si existen) para inspección..."
# Nombres esperados: raft_node1..raft_node12 (o raft1..raft4 según compose). Ajusta si es necesario.
# Aquí copiamos archivos comunes ubicados en /app/data/agenda.db dentro del container.

for node in raft_node1 raft_node2 raft_node3 raft_node4 raft_node5 raft_node6 raft_node7 raft_node8 raft_node9 raft_node10 raft_node11 raft_node12; do
  echo "--> intentando copiar DB de $node ..."
  # si el contenedor no existe, saltar
  if docker ps -a --format '{{.Names}}' | grep -q "^${node}$"; then
    out="tmp/${node}_agenda.db"
    docker cp "${node}:/app/data/agenda.db" "$out" 2>/dev/null || {
      echo "   no se encontró agenda.db en ${node}:/app/data/. Intentando otras rutas..."
      # prueba ruta alternativa
      docker cp "${node}:/app/agenda.db" "$out" 2>/dev/null || echo "   no se pudo extraer DB de $node"
    }
    if [ -f "$out" ]; then
      echo "   Archivo copiado -> $out (size: $(stat -c%s "$out") bytes)"
      # si tienes sqlite3 en host, muestra tablas
      if command -v sqlite3 >/dev/null 2>&1; then
        echo "   Tablas en $out:"; sqlite3 "$out" "SELECT name FROM sqlite_master WHERE type='table';" || true
      fi
    fi
  else
    echo "   Contenedor $node no encontrado (salta)."
  fi
done

echo
echo "SMOKE TEST finalizado. Revisa tmp/*.db y los logs de los contenedores si algo falló."

exit 0
