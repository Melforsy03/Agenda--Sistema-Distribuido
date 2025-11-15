# Agenda Distribuida - Sistema Distribuido

Sistema de agenda distribuida con arquitectura cliente-servidor separada.

## Arquitectura

El sistema está dividido en dos módulos principales:

1. **Servidor**: API REST con FastAPI + WebSocket server
2. **Cliente**: Interfaz web con Streamlit

## Estructura del proyecto

```
.
├── client/                 # Módulo cliente (Streamlit)
│   ├── ui/                 # Vistas de la interfaz
│   ├── services/           # Servicios del cliente
│   ├── app.py             # Aplicación principal
│   ├── requirements.txt   # Dependencias del cliente
│   └── Dockerfile         # Dockerfile del cliente
├── server/                # Módulo servidor (FastAPI)
│   ├── api/               # Endpoints de la API
│   ├── database/          # Capa de acceso a datos
│   ├── services/          # Lógica de negocio
│   ├── models/            # Modelos de datos
│   ├── main.py            # Aplicación principal
│   ├── requirements.txt   # Dependencias del servidor
│   └── Dockerfile         # Dockerfile del servidor
├── docker-compose.yml     # Orquestación de contenedores
└── requirements.txt       # Dependencias combinadas
```

## Requisitos

- Docker y Docker Compose
- Python 3.8+

## Ejecución con Docker (Recomendado)

```bash
# Construir y ejecutar los contenedores
docker-compose up --build

# La aplicación estará disponible en:
# Cliente (Streamlit): http://localhost:8501
# API (FastAPI): http://localhost:8000
# WebSocket: ws://localhost:8765
```

## Ejecución local sin Docker

### Servidor

```bash
# Navegar al directorio del servidor
cd server

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar el servidor
python services/main.py
```

### Cliente

```bash
# Navegar al directorio del cliente
cd client

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar el cliente
streamlit run app.py
```

## Variables de entorno

### Servidor
- `WEBSOCKET_HOST`: Host del servidor WebSocket (default: 0.0.0.0)
- `WEBSOCKET_PORT`: Puerto del servidor WebSocket (default: 8765)
- `DB_PATH`: Ruta al archivo de base de datos (default: agenda.db)

### Cliente
- `API_BASE_URL`: URL base de la API del servidor (default: http://localhost:8000)
- `WEBSOCKET_HOST`: Host del servidor WebSocket (default: localhost)
- `WEBSOCKET_PORT`: Puerto del servidor WebSocket (default: 8765)

## API Endpoints

### Autenticación
- `POST /auth/register` - Registrar nuevo usuario
- `POST /auth/login` - Iniciar sesión

### Usuarios
- `GET /users` - Listar todos los usuarios

### Grupos
- `POST /groups` - Crear grupo
- `GET /groups` - Listar grupos del usuario
- `GET /groups/{id}/members` - Listar miembros de un grupo
- `POST /groups/invite` - Invitar usuario a grupo
- `GET /groups/invitations` - Listar invitaciones pendientes
- `POST /groups/invitations/respond` - Responder invitación
- `GET /groups/invitations/count` - Contar invitaciones pendientes

### Eventos
- `POST /events` - Crear evento
- `GET /events` - Listar eventos del usuario
- `GET /events/detailed` - Listar eventos con detalles
- `GET /events/invitations` - Listar invitaciones a eventos
- `POST /events/invitations/respond` - Responder invitación a evento
- `GET /events/invitations/count` - Contar invitaciones a eventos pendientes

## WebSocket

El servidor WebSocket se utiliza para notificaciones en tiempo real entre usuarios.

### Mensajes del cliente al servidor:
- `{ "type": "auth", "user_id": <id> }` - Autenticación inicial
- `{ "type": "ping" }` - Mensaje de latido

### Mensajes del servidor al cliente:
- `{ "type": "auth_success" }` - Confirmación de autenticación
- `{ "type": "pong" }` - Respuesta a ping
- `{ "type": "group_invitation" }` - Notificación de invitación a grupo
- `{ "type": "event_invitation" }` - Notificación de invitación a evento
- `{ "type": "event_accepted" }` - Notificación de aceptación de evento
- `{ "type": "event_declined" }` - Notificación de rechazo de evento
- `{ "type": "event_cancelled" }` - Notificación de cancelación de evento
- `{ "type": "participant_left" }` - Notificación de salida de participante
- `{ "type": "new_group_member" }` - Notificación de nuevo miembro en grupo
- `{ "type": "removed_from_group" }` - Notificación de eliminación de grupo
- `{ "type": "group_deleted" }` - Notificación de eliminación de grupo