#!/bin/bash

# Iniciar servidor WebSocket en segundo plano
echo "Iniciando servidor WebSocket en puerto 8765..."
python -c "
import asyncio
import sys
import os
sys.path.append('/app')
from websocket_server import start_websocket_server

async def main():
    server = await start_websocket_server(host='0.0.0.0', port=8765)
    print(f'WebSocket server running on 0.0.0.0:8765')
    await server.wait_closed()

# Ejecutar en segundo plano
asyncio.ensure_future(main())
" &

# Esperar un momento para que WebSocket inicie
sleep 3

# Iniciar Streamlit
echo "Iniciando Streamlit en puerto 8501..."
exec streamlit run app.py --server.port=8501 --server.address=0.0.0.0