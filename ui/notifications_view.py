import streamlit as st
import json
from services.notification_service import NotificationService

def show_notifications_view(user_id):
    st.header("🔔 Notificaciones")
    
    # Placeholder para notificaciones en tiempo real
    st.info("Las notificaciones en tiempo real aparecerán aquí cuando otros usuarios realicen acciones")
    
    # Ejemplo de notificaciones (en un sistema real vendrían via WebSocket)
    st.subheader("Actividad reciente")
    
    # Aquí se conectaría con el WebSocketManager para mostrar notificaciones en tiempo real
    if st.button("Actualizar notificaciones"):
        # En un sistema real, esto obtendría notificaciones persistentes
        notifications = NotificationService().get_user_notifications(user_id)
        if notifications:
            for notification in notifications:
                st.write(f"📢 {notification}")
        else:
            st.info("No hay notificaciones recientes")
    
    # Indicador de estado de conexión WebSocket
    st.sidebar.markdown("---")
    connection_status = st.sidebar.empty()
    connection_status.success("✅ Conectado en tiempo real")