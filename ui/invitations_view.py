import streamlit as st
from services.group_service import GroupService
from services.event_service import EventService
import asyncio

def show_invitations_view(user_id):
    st.header("📧 Invitaciones pendientes")

    # Tabs para separar invitaciones a grupos y eventos
    tab1, tab2 = st.tabs(["👥 Grupos", "📅 Eventos"])

    with tab1:
        show_group_invitations(user_id)

    with tab2:
        show_event_invitations(user_id)


def show_group_invitations(user_id):
    """Mostrar invitaciones a grupos"""
    st.subheader("Invitaciones a grupos")
    invitations = GroupService().pending_invitations(user_id)

    if not invitations:
        st.info("No tienes invitaciones a grupos pendientes")
        return

    for inv in invitations:
        inv_id, group_name, inviter_name, created_at, group_id = inv
        with st.container():
            st.markdown(f"### 🏢 {group_name}")
            st.markdown(f"**Invitado por:** {inviter_name}")
            st.markdown(f"**Fecha:** {created_at}")

            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"✅ Aceptar", key=f"acc_grp_{inv_id}"):
                    async def accept_invitation():
                        return await GroupService().respond_invitation(inv_id, "accepted", user_id)
                    asyncio.run(accept_invitation())
                    st.success("Te uniste al grupo")
                    st.rerun()
            with col2:
                if st.button(f"❌ Rechazar", key=f"rej_grp_{inv_id}"):
                    async def reject_invitation():
                        return await GroupService().respond_invitation(inv_id, "declined", user_id)
                    asyncio.run(reject_invitation())
                    st.warning("Invitación rechazada")
                    st.rerun()
            st.markdown("---")


def show_event_invitations(user_id):
    """Mostrar invitaciones a eventos"""
    st.subheader("Invitaciones a eventos")
    event_service = EventService()
    invitations = event_service.get_pending_event_invitations(user_id)

    if not invitations:
        st.info("No tienes invitaciones a eventos pendientes")
        return

    for inv in invitations:
        event_id, title, description, start_time, end_time, creator_name, group_name, is_group_event, group_id = inv

        with st.container():
            st.markdown(f"### 📅 {title}")
            st.markdown(f"**Descripción:** {description or 'Sin descripción'}")
            st.markdown(f"**Creador:** {creator_name}")

            if is_group_event and group_name:
                st.markdown(f"**Grupo:** 👥 {group_name}")

            st.markdown(f"**⏰ Inicio:** {start_time}")
            st.markdown(f"**⏰ Fin:** {end_time}")

            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"✅ Aceptar", key=f"acc_evt_{event_id}"):
                    async def accept_event():
                        return await event_service.respond_to_event_invitation(event_id, user_id, True)

                    success, message = asyncio.run(accept_event())
                    if success:
                        st.success(f"✅ {message}")
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")

            with col2:
                if st.button(f"❌ Rechazar", key=f"rej_evt_{event_id}"):
                    async def reject_event():
                        return await event_service.respond_to_event_invitation(event_id, user_id, False)

                    success, message = asyncio.run(reject_event())
                    if success:
                        st.warning(f"⚠️ {message}")
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")

            st.markdown("---")
