#!/usr/bin/env bash
set -e

echo "🚀 Iniciando Agenda Distribuida..."

# --- 1. Iniciar el backend FastAPI + WebSocket ---
echo "▶️ Iniciando backend (FastAPI + WebSocket)..."
python -m main &
BACKEND_PID=$!

# Esperar a que levante el backend (puerto 8000 y 8765)
sleep 4

# --- 2. Iniciar el frontend Streamlit ---
echo "▶️ Iniciando frontend (Streamlit)..."
streamlit run app.py --server.port=8501 --server.address=0.0.0.0 &
FRONTEND_PID=$!

# --- 3. Mostrar URLs ---
echo "============================================"
echo "✅ Agenda Distribuida en ejecución"
echo "Frontend (Streamlit): http://localhost:8501"
echo "Backend (FastAPI):   http://localhost:8000"
echo "WebSocket:           ws://localhost:8765"
echo "============================================"
echo
echo "Para detener todo, usa: ./stop_services.sh"
echo

# Mantener script vivo hasta que se cierre alguno de los procesos
wait $BACKEND_PID $FRONTEND_PID
