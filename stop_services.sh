#!/usr/bin/env bash
set -e

echo "🛑 Deteniendo Agenda Distribuida..."

# Matar procesos de Python/Streamlit que estén usando esos puertos
pids=$(lsof -ti:8000,8501,8765 || true)
if [[ -n "$pids" ]]; then
  echo "Encontrados procesos en puertos 8000/8501/8765. Cerrando..."
  kill -9 $pids || true
else
  echo "No hay procesos activos en esos puertos."
fi

echo "✅ Servicios detenidos."
