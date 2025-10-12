import streamlit as st
from services.group_service import GroupService
import asyncio

def show_invitations_view(user_id):
    st.header("📧 Invitaciones pendientes")

    invitations = GroupService().pending_invitations(user_id)

    if not invitations:
        st.info("No tienes invitaciones")
        return

    for inv in invitations:
        inv_id, group_name, inviter_name, created_at, group_id = inv
        st.markdown(f"**Grupo:** {group_name} | Invitado por: {inviter_name} | Fecha: {created_at}")
        col1, col2 = st.columns(2)
        with col1:
            if st.button(f"Aceptar {group_name}", key=f"acc_{inv_id}"):
                async def accept_invitation():
                    return await GroupService().respond_invitation(inv_id, "accepted", user_id)
                asyncio.run(accept_invitation())
                st.success("Te uniste al grupo")
                st.rerun()
        with col2:
            if st.button(f"Rechazar {group_name}", key=f"rej_{inv_id}"):
                async def reject_invitation():
                    return await GroupService().respond_invitation(inv_id, "declined", user_id)
                asyncio.run(reject_invitation())
                st.warning("Invitación rechazada")
                st.rerun()
