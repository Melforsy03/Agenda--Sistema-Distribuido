import streamlit as st
from services.group_service import GroupService
from services.auth_service import AuthService

def show_groups_view(user_id):
    st.header("👥 Mis grupos")

    # --- Crear nuevo grupo ---
    with st.expander("Crear grupo", expanded=False):
        name = st.text_input("Nombre del grupo")
        description = st.text_area("Descripción")
        is_hierarchical = st.checkbox("Jerárquico")
        users = AuthService().list_users()
        options = {u[1]: u[0] for u in users if u[0] != user_id}
        selected = st.multiselect("Invitar miembros", list(options.keys()))

        if st.button("Crear grupo"):
            group_id, invited = GroupService().create_group(
                name, description, is_hierarchical, user_id,
                [options[s] for s in selected]
            )
            if group_id:
                st.success(f"✅ Grupo creado (invitaciones enviadas: {invited})")
                st.rerun()
            else:
                st.error("❌ Ese grupo ya existe")

    # --- Listar grupos ---
    groups = GroupService().list_user_groups(user_id)
    if groups:
        for g in groups:
            gid, gname, hier = g
            st.subheader(f"🏢 {gname} {'(Jerárquico)' if hier else ''}")
            members = GroupService().list_group_members(gid)
            st.write("Miembros: " + ", ".join([m[1] for m in members]))
    else:
        st.info("No perteneces a ningún grupo")
