import streamlit as st
from services.group_service import GroupService
from services.auth_service import AuthService
from services.visualization_service import VisualizationService
from services.hierarchy_service import HierarchyService
import asyncio

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
            # NUEVO: Usar versión asíncrona
            async def create_group_async():
                return await GroupService().create_group(
                    name, description, is_hierarchical, user_id,
                    [options[s] for s in selected]
                )
            
            group_id, message = asyncio.run(create_group_async())
            if group_id:
                st.success(f"✅ Grupo creado - {message}")
                st.rerun()
            else:
                st.error(f"❌ {message}")

    # --- Listar grupos con nuevas funcionalidades ---
    groups = GroupService().list_user_groups(user_id)
    if groups:
        for g in groups:
            gid, gname, hier = g
            group_service = GroupService()
            is_leader = group_service.is_leader(user_id, gid)

            # Header con indicador de líder
            leader_badge = "👑 LÍDER - " if is_leader else ""
            st.subheader(f"{leader_badge}🏢 {gname} {'👑 (Jerárquico)' if hier else '👥 (No jerárquico)'}")

            # Opciones de visualización
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button(f"📊 Ver agendas", key=f"view_{gid}"):
                    st.session_state.current_group_view = gid
            with col2:
                if st.button(f"🕐 Disponibilidad", key=f"availability_{gid}"):
                    st.session_state.common_availability_group = gid
            with col3:
                if is_leader:
                    if st.button(f"✏️ Editar grupo", key=f"edit_{gid}"):
                        st.session_state[f'editing_group_{gid}'] = True

            # NUEVO: Panel de edición para líderes
            if is_leader and st.session_state.get(f'editing_group_{gid}', False):
                show_group_edit_panel(user_id, gid, gname)

            # Mostrar miembros con sus roles y opciones de gestión
            members = GroupService().list_group_members(gid)
            hierarchy_service = HierarchyService()

            leaders = []
            regular_members = []
            member_details = []

            for member_id, username in members:
                role = hierarchy_service.get_user_role_in_group(member_id, gid)
                member_details.append((member_id, username, role))
                if role == "leader":
                    leaders.append(username)
                else:
                    regular_members.append(username)

            st.write("**Líderes:** " + ", ".join([f"👑 {l}" for l in leaders]))
            st.write("**Miembros:** " + ", ".join(regular_members))

            # NUEVO: Gestión de miembros para líderes
            if is_leader:
                with st.expander("👥 Gestionar miembros"):
                    show_member_management(user_id, gid, member_details)

            # Mostrar visualización de agendas si está activa
            if hasattr(st.session_state, 'current_group_view') and st.session_state.current_group_view == gid:
                show_group_agendas(user_id, gid)

            # Mostrar disponibilidad común si está activa
            if hasattr(st.session_state, 'common_availability_group') and st.session_state.common_availability_group == gid:
                show_common_availability(gid)

            st.markdown("---")
    else:
        st.info("No perteneces a ningún grupo")

def show_group_edit_panel(user_id, group_id, current_name):
    """Panel de edición para líderes del grupo"""
    st.markdown("---")
    st.subheader("✏️ Editar grupo")

    group_service = GroupService()
    group_info = group_service.get_group_info(group_id)

    if group_info:
        _, current_name, current_desc, _, _ = group_info

        col1, col2 = st.columns(2)
        with col1:
            new_name = st.text_input("Nombre del grupo", value=current_name, key=f"edit_name_{group_id}")
        with col2:
            new_desc = st.text_area("Descripción", value=current_desc or "", key=f"edit_desc_{group_id}")

        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.button("💾 Guardar cambios", key=f"save_{group_id}"):
                success, message = group_service.update_group(
                    group_id, user_id,
                    name=new_name if new_name != current_name else None,
                    description=new_desc if new_desc != current_desc else None
                )
                if success:
                    st.success(f"✅ {message}")
                    st.session_state[f'editing_group_{group_id}'] = False
                    st.rerun()
                else:
                    st.error(f"❌ {message}")

        with col_cancel:
            if st.button("❌ Cancelar", key=f"cancel_edit_{group_id}"):
                st.session_state[f'editing_group_{group_id}'] = False
                st.rerun()

def show_member_management(leader_id, group_id, member_details):
    """Panel de gestión de miembros para líderes"""
    st.markdown("**Invitar nuevos miembros**")

    # Obtener usuarios que no están en el grupo
    all_users = AuthService().list_users()
    current_member_ids = [m[0] for m in member_details]
    available_users = {u[1]: u[0] for u in all_users if u[0] not in current_member_ids}

    if available_users:
        selected_user = st.selectbox(
            "Seleccionar usuario",
            options=list(available_users.keys()),
            key=f"invite_user_{group_id}"
        )

        if st.button("📧 Enviar invitación", key=f"send_invite_{group_id}"):
            async def invite_user_async():
                return await GroupService().invite_user(
                    group_id,
                    available_users[selected_user],
                    leader_id
                )

            success, message = asyncio.run(invite_user_async())
            if success:
                st.success(f"✅ {message}")
            else:
                st.error(f"❌ {message}")
    else:
        st.info("No hay usuarios disponibles para invitar")

    st.markdown("---")
    st.markdown("**Eliminar miembros**")

    # Mostrar miembros que pueden ser eliminados (no líderes)
    removable_members = [(m[0], m[1]) for m in member_details if m[2] != "leader"]

    if removable_members:
        for member_id, username in removable_members:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"👤 {username}")
            with col2:
                if st.button("🗑️ Eliminar", key=f"remove_{group_id}_{member_id}"):
                    async def remove_member_async():
                        return await GroupService().remove_member(group_id, leader_id, member_id)

                    success, message = asyncio.run(remove_member_async())
                    if success:
                        st.success(f"✅ {message}")
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")
    else:
        st.info("No hay miembros regulares para eliminar")

def show_group_agendas(viewer_id, group_id):
    """Mostrar agendas del grupo con control de acceso"""
    st.subheader("📊 Agendas del grupo")

    date_col1, date_col2 = st.columns(2)
    with date_col1:
        start_date = st.date_input("Fecha inicio", key=f"start_{group_id}")
    with date_col2:
        end_date = st.date_input("Fecha fin", key=f"end_{group_id}")

    if st.button("🔍 Cargar agendas", key=f"load_agendas_{group_id}"):
        viz_service = VisualizationService()
        group_agendas, error = viz_service.get_group_agendas(
            viewer_id, group_id,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )

        if error:
            st.error(f"❌ {error}")
        else:
            if not group_agendas:
                st.info("No hay miembros con agendas visibles")
            else:
                for username, user_data in group_agendas.items():
                    with st.expander(f"📅 Agenda de {username}", expanded=True):
                        events = user_data["events"]
                        if events:
                            for event in events:
                                st.markdown(f"### {event['title']}")
                                if event['description']:
                                    st.write(f"📝 {event['description']}")
                                st.write(f"🕐 **Inicio:** {event['start_time']}")
                                st.write(f"🕐 **Fin:** {event['end_time']}")
                                if event['is_group_event'] and event['group_name']:
                                    st.write(f"👥 **Grupo:** {event['group_name']}")
                                st.markdown("---")
                        else:
                            st.info("No hay eventos en este período")

def show_common_availability(group_id):
    """Mostrar horarios comunes disponibles"""
    st.subheader("🕐 Horarios comunes disponibles")

    date_col1, date_col2 = st.columns(2)
    with date_col1:
        start_date = st.date_input("Fecha inicio", key=f"avail_start_{group_id}")
    with date_col2:
        end_date = st.date_input("Fecha fin", key=f"avail_end_{group_id}")

    duration = st.slider("Duración requerida (horas)", 1, 8, 2, key=f"duration_{group_id}")

    if st.button("🔍 Buscar horarios disponibles", key=f"search_avail_{group_id}"):
        viz_service = VisualizationService()
        available_slots = viz_service.get_common_availability(
            group_id,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d'),
            duration
        )

        if available_slots:
            st.success(f"✅ Encontrados {len(available_slots)} horarios disponibles")

            # Mostrar en una tabla más organizada
            st.markdown("### Horarios disponibles para todos:")

            for idx, slot in enumerate(available_slots[:20], 1):  # Mostrar máximo 20
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**{idx}.** 📅 {slot['start_time']} ➡️ {slot['end_time']}")
                with col2:
                    if st.button("Agendar", key=f"schedule_{group_id}_{idx}"):
                        st.info("Redirigiendo a crear evento...")
                        # Aquí se podría pre-llenar el formulario de crear evento

            if len(available_slots) > 20:
                st.info(f"Mostrando primeros 20 de {len(available_slots)} horarios disponibles")
        else:
            st.warning("❌ No hay horarios comunes disponibles en este período")
            st.info("Intenta con un período de tiempo más amplio o menor duración")