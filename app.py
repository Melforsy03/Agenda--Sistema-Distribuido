import streamlit as st
import asyncio
import threading
import os
import time
from ui.login_view import show_login_page
from ui.calendar_view import show_calendar_view
from ui.event_view import show_create_event_view
from ui.group_view import show_groups_view
from ui.invitations_view import show_invitations_view
from ui.notifications_view import show_notifications_view
from services.auth_service import AuthService
from services.session_manager import SessionManager

# Configuración de la página
st.set_page_config(
    page_title="Agenda Distribuida",
    page_icon="📅",
    layout="wide"
)

def get_websocket_url():
    """Obtener URL del WebSocket basado en el entorno"""
    # En Docker Swarm, usar el host del manager
    host = os.getenv('WEBSOCKET_HOST', 'localhost')
    port = os.getenv('WEBSOCKET_PORT', '8765')
    return f"ws://{host}:{port}"

def start_websocket_server():
    """Iniciar servidor WebSocket en un hilo separado"""
    from services.websocket_server import start_websocket_server as ws_start
    asyncio.run(ws_start())

def restore_session():
    """Restaurar sesión desde query params o localStorage"""
    session_manager = SessionManager()

    # Intentar obtener token de los query params
    if 'session_token' in st.query_params:
        token = st.query_params['session_token']
        session_data = session_manager.get_session(token)

        if session_data:
            st.session_state.logged_in = True
            st.session_state.username = session_data['username']
            st.session_state.user_id = session_data['user_id']
            st.session_state.session_token = token
            return True

    return False

def main():
    # Limpiar sesiones antiguas periódicamente
    session_manager = SessionManager()
    session_manager.cleanup_old_sessions()

    # Inicializar estado de sesión
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    # Intentar restaurar sesión si no está logueado
    if not st.session_state.logged_in:
        restore_session()

    if not st.session_state.logged_in:
        show_login_page()
    else:
        # Sidebar con información de conexión
        st.sidebar.title(f"👋 Hola, {st.session_state.username}")

        # Mostrar estado de conexión WebSocket
        websocket_url = get_websocket_url()
        st.sidebar.info(f"🌐 Conectado a: {websocket_url}")

        auth_service = AuthService()
        user_id = auth_service.get_user_id(st.session_state.username)
        st.session_state.user_id = user_id

        # Obtener conteos de invitaciones pendientes
        from services.group_service import GroupService
        from services.event_service import EventService

        group_service = GroupService()
        event_service = EventService()

        groups_count = group_service.get_pending_invitations_count(user_id)
        events_count = event_service.get_pending_invitations_count(user_id)
        total_invitations = groups_count + events_count

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
            # Eliminar sesión del servidor
            if 'session_token' in st.session_state:
                session_manager = SessionManager()
                session_manager.delete_session(st.session_state.session_token)

            # Limpiar query params
            if 'session_token' in st.query_params:
                del st.query_params['session_token']

            # Limpiar session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]

            st.rerun()
        
        # Mostrar página seleccionada
        if page == "📅 Calendario":
            show_calendar_view(user_id)
        elif page == "➕ Crear Evento":
            show_create_event_view(user_id)
        elif page == "👥 Grupos":
            show_groups_view(user_id)
        elif page.startswith("📧 Invitaciones"):  # Maneja tanto con badge como sin badge
            show_invitations_view(user_id)
        elif page == "🔔 Notificaciones":
            show_notifications_view(user_id)

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

    # Solo intentar iniciar el WebSocket si el puerto 8765 está libre
    # y no estamos en Docker
    if os.getenv('DOCKER_ENV') != 'true':
        websocket_port = int(os.getenv('WEBSOCKET_PORT', '8765'))
        if not is_port_in_use(websocket_port):
            try:
                thread = threading.Thread(target=start_websocket_server, daemon=True)
                thread.start()
            except Exception as e:
                # El error se mostrará en la consola pero no bloqueará la app
                pass

    main()