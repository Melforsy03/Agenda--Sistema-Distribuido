import streamlit as st
from ui.login_view import show_login_page
from ui.calendar_view import show_calendar_view
from ui.event_view import show_create_event_view
from ui.group_view import show_groups_view
from ui.invitations_view import show_invitations_view
from services.auth_service import AuthService

# Estado de sesión
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None

if st.session_state.logged_in:
    user_id = AuthService().get_user_id(st.session_state.username)

    # Sidebar de navegación
    with st.sidebar:
        st.title(f"👋 Hola {st.session_state.username}")
        option = st.radio(
            "Navegación",
            ["📅 Calendario", "➕ Evento", "👥 Grupos", "📧 Invitaciones"]
        )

        st.markdown("---")
        if st.button("🚪 Cerrar sesión"):
            st.session_state.logged_in = False
            st.session_state.username = None
            st.rerun()

    # Contenido principal
    if option == "📅 Calendario":
        show_calendar_view(user_id)
    elif option == "➕ Evento":
        show_create_event_view(user_id)
    elif option == "👥 Grupos":
        show_groups_view(user_id)
    elif option == "📧 Invitaciones":
        show_invitations_view(user_id)

else:
    show_login_page()
