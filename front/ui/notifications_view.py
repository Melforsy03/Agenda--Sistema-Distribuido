import streamlit as st

# Store notifications in session state
if 'notifications' not in st.session_state:
    st.session_state.notifications = []

def notification_handler(data):
    """Handle incoming WebSocket notifications"""
    try:
        # Add notification to session state
        notification_text = f"📢 {data.get('type', 'Notificación')}: {data.get('message', 'Nueva notificación')}"
        st.session_state.notifications.append(notification_text)
        # Rerun to update the UI
        st.rerun()
    except Exception as e:
        # Handle case where rerun is not available
        pass

def show_notifications_view(user_id, api_client, token, ws_client):
    st.header("🔔 Notificaciones")
    
    # Register handler for WebSocket notifications
    try:
        # Check if handlers are already registered to avoid duplicates
        handlers_key = f"notification_handlers_registered_{user_id}"
        if handlers_key not in st.session_state:
            ws_client.register_handler("group_invitation", notification_handler)
            ws_client.register_handler("event_invitation", notification_handler)
            ws_client.register_handler("event_accepted", notification_handler)
            ws_client.register_handler("event_declined", notification_handler)
            ws_client.register_handler("event_cancelled", notification_handler)
            ws_client.register_handler("participant_left", notification_handler)
            ws_client.register_handler("new_group_member", notification_handler)
            ws_client.register_handler("removed_from_group", notification_handler)
            ws_client.register_handler("group_deleted", notification_handler)
            st.session_state[handlers_key] = True
    except Exception as e:
        st.warning(f"No se pudieron registrar los manejadores de notificaciones: {e}")
    
    # Display notifications
    st.subheader("Actividad reciente")
    
    if st.session_state.notifications:
        # Show notifications in reverse order (newest first)
        for notification in reversed(st.session_state.notifications):
            st.write(notification)
    else:
        st.info("No hay notificaciones recientes")
    
    # Clear notifications button
    if st.button("🗑️ Limpiar notificaciones"):
        st.session_state.notifications = []
        st.rerun()
    
    # Indicador de estado de conexión WebSocket
    st.sidebar.markdown("---")
    connection_status = st.sidebar.empty()
    try:
        if ws_client.connected:
            connection_status.success("✅ Conectado en tiempo real")
        else:
            connection_status.warning("⚠️ Desconectado")
    except:
        connection_status.error("❌ Error de conexión")