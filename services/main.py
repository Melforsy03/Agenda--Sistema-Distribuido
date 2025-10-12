import asyncio
from services.websocket_server import start_websocket_server
from services.auth_service import AuthService
from services.group_service import GroupService
from services.event_service import EventService
#from services.visualization_service import VisualizationService
import uvicorn
from fastapi import FastAPI

app = FastAPI(title="Agenda Distribuida")

# Inicializar servicios
auth_service = AuthService()
group_service = GroupService()
event_service = EventService()
#visualization_service = VisualizationService()

@app.on_event("startup")
async def startup_event():
    """Iniciar servidor WebSocket al arrancar la aplicación"""
    asyncio.create_task(start_websocket_server())

# Aquí irían los endpoints REST de la API...
@app.get("/")
async def root():
    return {"message": "Agenda Distribuida API"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)