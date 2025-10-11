import asyncio
import websockets
import json
import logging
import os
from services.websocket_manager import websocket_manager
from services.auth_service import AuthService

logging.basicConfig(level=logging.INFO)
auth_service = AuthService()

async def websocket_handler(websocket, path):
    """Manejador principal de conexiones WebSocket"""
    user_id = None
    
    try:
        # Esperar autenticación inicial
        auth_message = await websocket.recv()
        auth_data = json.loads(auth_message)
        
        if auth_data.get('type') == 'auth':
            user_id = auth_data.get('user_id')
            
            if user_id:
                await websocket_manager.connect(websocket, user_id)
                logging.info(f"Usuario {user_id} conectado via WebSocket desde {websocket.remote_address}")
                
                await websocket.send(json.dumps({
                    "type": "auth_success",
                    "message": "Conexión WebSocket establecida"
                }))
            else:
                await websocket.close()
                return
        
        # Mantener conexión activa
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get('type') == 'ping':
                    await websocket.send(json.dumps({"type": "pong"}))
                    
            except json.JSONDecodeError:
                logging.error("Mensaje JSON inválido")
    
    except websockets.exceptions.ConnectionClosed:
        logging.info(f"Conexión WebSocket cerrada para usuario {user_id}")
    finally:
        if user_id:
            await websocket_manager.disconnect(websocket, user_id)

async def start_websocket_server(host='0.0.0.0', port=8765):
    """Iniciar servidor WebSocket"""
    # Usar host desde variable de entorno o default
    host = os.getenv('WEBSOCKET_HOST', host)
    port = int(os.getenv('WEBSOCKET_PORT', port))
    
    server = await websockets.serve(websocket_handler, host, port)
    logging.info(f"Servidor WebSocket iniciado en ws://{host}:{port}")
    return server