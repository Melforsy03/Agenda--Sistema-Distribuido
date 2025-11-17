import streamlit as st
import asyncio
import threading
import os
import time
import warnings
import logging
from ui.login_view import show_login_page
from ui.calendar_view import show_calendar_view
from ui.event_view import show_create_event_view
from ui.group_view import show_groups_view
from ui.invitations_view import show_invitations_view
from ui.notifications_view import show_notifications_view
from services.api_client import APIClient
from services.websocket_client import WebSocketClient

# Suppress asyncio warnings about unclosed resources
warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*coroutine.*was never awaited.*')
warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*Event loop is closed.*')
warnings.filterwarnings('ignore', category=ResourceWarning)

# Configure logging to suppress certain messages
logging.getLogger('asyncio').setLevel(logging.ERROR)

# Configuración de la página
st.set_page_config(
    page_title="Agenda Distribuida",
    page_icon="📅",
    layout="wide"
)

# Initialize API client
api_client = APIClient()

# Initialize WebSocket client
ws_client = WebSocketClient()

def get_websocket_url():
    """Obtener URL del WebSocket basado en el entorno"""
    # En Docker Swarm, usar el host del manager
    host = os.getenv('WEBSOCKET_HOST', 'localhost')
    port = os.getenv('WEBSOCKET_PORT', '8767')
    return f"ws://{host}:{port}"

async def connect_websocket(user_id):
    """Connect to WebSocket server"""
    # If already connected, no need to reconnect
    if ws_client.connected:
        return True
    
    try:
        success = await ws_client.connect(user_id)
        if success:
            # Start listening for messages in a separate task
            try:
                # Store the listener task so we can manage it later
                ws_client.listener_task = asyncio.create_task(ws_client.listen())
            except Exception as e:
                if "Event loop is closed" in str(e):
                    ws_client.connected = False
                    return False
                else:
                    raise e
        return success
    except Exception as e:
        st.error(f"Error al conectar WebSocket: {str(e)}")
        return False

async def disconnect_websocket():
    """Disconnect from WebSocket server"""
    # Signal the client to stop listening
    ws_client.should_stop = True
    
    try:
        await asyncio.wait_for(ws_client.disconnect(), timeout=3.0)
    except asyncio.TimeoutError:
        # Force cleanup if timeout
        ws_client.connected = False
        ws_client.listening = False
        if ws_client.listener_task:
            ws_client.listener_task.cancel()
    except Exception:
        pass  # Ignore errors during disconnect

def restore_session():
    """Restaurar sesión desde query params o localStorage"""
    # Intentar obtener token de los query params
    if 'session_token' in st.query_params:
        token = st.query_params['session_token']
        try:
            # Validate token by making a simple API call
            users = api_client.list_users(token)
            
            # Get user_id from query params if available
            if 'user_id' in st.query_params:
                try:
                    user_id = int(st.query_params['user_id'])
                    # Find username for this user_id
                    username = None
                    for user in users:
                        if user[0] == user_id:  # user[0] is user_id
                            username = user[1]  # user[1] is username
                            break
                    
                    if username:
                        # Restore complete session state
                        st.session_state.logged_in = True
                        st.session_state.session_token = token
                        st.session_state.user_id = user_id
                        st.session_state.username = username
                        st.session_state.websocket_connected = False
                        return True
                except (ValueError, IndexError):
                    pass
            
            # If we couldn't restore user_id from query params, token is still valid
            # but we need to get user info from somewhere else
            st.session_state.logged_in = True
            st.session_state.session_token = token
            st.session_state.websocket_connected = False
            return True
        except:
            # Token is invalid, remove it
            if 'session_token' in st.query_params:
                del st.query_params['session_token']
            if 'user_id' in st.query_params:
                del st.query_params['user_id']
            return False

    return False

def main():
    # Inicializar estado de sesión
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    # Intentar restaurar sesión si no está logueado
    if not st.session_state.logged_in:
        restore_session()

    if not st.session_state.logged_in:
        show_login_page(api_client)
    else:
        # Make sure username is in session state
        if 'username' not in st.session_state:
            # Try to get username from API
            try:
                users = api_client.list_users(st.session_state.session_token)
                # Find current user ID
                for user in users:
                    if user[0] == st.session_state.user_id:  # user[0] is user_id
                        st.session_state.username = user[1]  # user[1] is username
                        break
            except Exception as e:
                st.error(f"Error getting user info: {e}")
                st.session_state.logged_in = False
                st.rerun()

        # Sidebar con información de conexión
        st.sidebar.title(f"👋 Hola, {st.session_state.username}")

        # Mostrar estado de conexión WebSocket
        websocket_url = get_websocket_url()
        st.sidebar.info(f"🌐 Conectado a: {websocket_url}")

        # Get user ID from token if not in session state
        if 'user_id' not in st.session_state:
            try:
                users = api_client.list_users(st.session_state.session_token)
                # Find current user ID
                for user in users:
                    if user[1] == st.session_state.username:  # user[1] is username
                        st.session_state.user_id = user[0]  # user[0] is user_id
                        break
            except Exception as e:
                st.error(f"Error getting user info: {e}")
                st.session_state.logged_in = False
                st.rerun()

        # Connect to WebSocket if not already connected
        if 'websocket_connected' not in st.session_state or not st.session_state.websocket_connected:
            try:
                # Run async function in a new event loop
                async def connect():
                    return await connect_websocket(st.session_state.user_id)
                
                # Create a new event loop for this operation
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    success = loop.run_until_complete(connect())
                    loop.close()
                    
                    st.session_state.websocket_connected = success
                    if not success:
                        st.sidebar.error("❌ No se pudo conectar al servidor WebSocket")
                except Exception as e:
                    if "Event loop is closed" in str(e):
                        st.session_state.websocket_connected = False
                        st.sidebar.warning("⚠️ No se pudo iniciar WebSocket en este entorno")
                    else:
                        st.sidebar.error(f"❌ Error de conexión WebSocket: {e}")
            except Exception as e:
                st.sidebar.error(f"❌ Error de conexión WebSocket: {e}")

        # Obtener conteos de invitaciones pendientes
        try:
            groups_count_data = api_client.get_pending_invitations_count(st.session_state.session_token)
            events_count_data = api_client.get_pending_event_invitations_count(st.session_state.session_token)
            groups_count = groups_count_data.get("count", 0)
            events_count = events_count_data.get("count", 0)
            total_invitations = groups_count + events_count
        except Exception as e:
            st.error(f"Error getting invitation counts: {e}")
            groups_count = 0
            events_count = 0
            total_invitations = 0

        # Guardar conteo anterior para detectar cambios
        if 'previous_invitations_count' not in st.session_state:
            st.session_state.previous_invitations_count = total_invitations

        # Auto-refresh: Si hay cambios en invitaciones, actualizar
        if st.session_state.previous_invitations_count != total_invitations:
            st.session_state.previous_invitations_count = total_invitations

        # Construir etiquetas con badges
        invitations_label = f"📧 Invitaciones ({total_invitations})" if total_invitations > 0 else "📧 Invitaciones"

        # Verificar si hay una vista específica solicitada
        if 'current_view' in st.session_state:
            requested_view = st.session_state.pop('current_view')
            if requested_view == 'events':
                default_page = "➕ Crear Evento"
            else:
                default_page = "📅 Calendario"
        else:
            default_page = "📅 Calendario"

        # Navegación
        page = st.sidebar.radio(
            "Navegación",
            ["📅 Calendario", "➕ Crear Evento", "👥 Grupos", invitations_label, "🔔 Notificaciones"],
            index=["📅 Calendario", "➕ Crear Evento", "👥 Grupos", invitations_label, "🔔 Notificaciones"].index(default_page) if default_page in ["📅 Calendario", "➕ Crear Evento", "👥 Grupos", invitations_label, "🔔 Notificaciones"] else 0
        )
        
        if st.sidebar.button("🚪 Cerrar sesión"):
            # Signal WebSocket client to stop listening before disconnecting
            ws_client.should_stop = True
            
            # Disconnect WebSocket before logging out
            try:
                async def disconnect():
                    await disconnect_websocket()
                
                # Only attempt to disconnect if we can create a new event loop
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(disconnect())
                    loop.close()
                except Exception:
                    pass  # Ignore errors during disconnect
            except Exception:
                pass  # Ignore errors during disconnect on logout
            
            # Limpiar query params
            if 'session_token' in st.query_params:
                del st.query_params['session_token']
            if 'user_id' in st.query_params:
                del st.query_params['user_id']

            # Limpiar session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]

            st.rerun()
        
        # Mostrar página seleccionada
        if page == "📅 Calendario":
            show_calendar_view(st.session_state.user_id, api_client, st.session_state.session_token)
        elif page == "➕ Crear Evento":
            show_create_event_view(st.session_state.user_id, api_client, st.session_state.session_token)
        elif page == "👥 Grupos":
            show_groups_view(st.session_state.user_id, api_client, st.session_state.session_token)
        elif page.startswith("📧 Invitaciones"):  # Maneja tanto con badge como sin badge
            show_invitations_view(st.session_state.user_id, api_client, st.session_state.session_token)
        elif page == "🔔 Notificaciones":
            show_notifications_view(st.session_state.user_id, api_client, st.session_state.session_token, ws_client)

# Iniciar WebSocket solo si no está ya corriendo
if __name__ == "__main__":
    # Usar un archivo de bandera global en lugar de session_state
    # porque session_state se reinicia en cada recarga de Streamlit
    import socket

    def is_port_in_use(port):
        """Verificar si un puerto está en uso"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', port))
                return False
            except OSError:
                return True

    # Solo intentar iniciar el WebSocket si el puerto 8767 está libre
    # y no estamos en Docker
    if os.getenv('DOCKER_ENV') != 'true':
        websocket_port = int(os.getenv('WEBSOCKET_PORT', '8767'))
        if not is_port_in_use(websocket_port):
            # Note: We're keeping the WebSocket server in the client for now
            # In a production environment, this would be in the server
            pass

    main()