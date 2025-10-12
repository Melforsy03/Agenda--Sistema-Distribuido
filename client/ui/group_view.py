import streamlit as st
import asyncio
from datetime import datetime, timedelta

def show_groups_view(user_id, api_client, token):
    st.header("👥 Mis grupos")

    # --- Crear nuevo grupo ---
    with st.expander("Crear grupo", expanded=False):
        name = st.text_input("Nombre del grupo")
        description = st.text_area("Descripción")
        is_hierarchical = st.checkbox("Jerárquico")
        try:
            users = api_client.list_users(token)
            options = {u[1]: u[0] for u in users if u[0] != user_id}
            selected = st.multiselect("Invitar miembros", list(options.keys()))

            if st.button("Crear grupo"):
                try:
                    members = [options[s] for s in selected]
                    result = api_client.create_group(name, description, is_hierarchical, token, members)
                    st.success(f"✅ Grupo creado - {result['message']}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al crear grupo: {str(e)}")
        except Exception as e:
            st.error(f"Error al cargar usuarios: {str(e)}")

    # --- Listar grupos con nuevas funcionalidades ---
    try:
        groups = api_client.list_user_groups(token)
        if groups:
            for g in groups:
                gid, gname, hier = g
                # Check if user is leader
                try:
                    group_info = api_client.get_group_info(gid, token)
                    is_leader = group_info['creator_id'] == user_id
                except:
                    is_leader = False

                # Header con indicador de líder
                leader_badge = "👑 LÍDER - " if is_leader else ""
                st.subheader(f"{leader_badge}🏢 {gname} {'👑 (Jerárquico)' if hier else '👥 (No jerárquico)'}")

                # Opciones de visualización
                if is_leader:
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        if st.button(f"📊 Ver agendas", key=f"view_{gid}"):
                            st.session_state.current_group_view = gid
                    with col2:
                        if st.button(f"🕐 Disponibilidad", key=f"availability_{gid}"):
                            st.session_state.common_availability_group = gid
                    with col3:
                        if st.button(f"✏️ Editar grupo", key=f"edit_{gid}"):
                            st.session_state[f'editing_group_{gid}'] = True
                    with col4:
                        if st.button(f"🗑️", key=f"delete_btn_{gid}", help="Eliminar grupo"):
                            st.session_state[f'deleting_group_{gid}'] = True
                else:
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(f"📊 Ver agendas", key=f"view_{gid}"):
                            st.session_state.current_group_view = gid
                    with col2:
                        if st.button(f"🕐 Disponibilidad", key=f"availability_{gid}"):
                            st.session_state.common_availability_group = gid

                # Panel de edición para líderes
                if is_leader and st.session_state.get(f'editing_group_{gid}', False):
                    show_group_edit_panel(user_id, gid, gname, api_client, token)

                # Panel de confirmación de eliminación
                if is_leader and st.session_state.get(f'deleting_group_{gid}', False):
                    show_delete_group_confirmation(user_id, gid, gname, api_client, token)

                # Mostrar miembros con sus roles y opciones de gestión
                try:
                    members = api_client.list_group_members(gid, token)
                    # Note: Hierarchy service functionality would need to be implemented in the API
                    # For now, we'll skip the hierarchical roles
                    leaders = []
                    regular_members = [username for _, username in members]

                    st.write("**Líderes:** " + ", ".join([f"👑 {l}" for l in leaders]))
                    st.write("**Miembros:** " + ", ".join(regular_members))

                    # NUEVO: Gestión de miembros para líderes
                    if is_leader:
                        with st.expander("👥 Gestionar miembros"):
                            show_member_management(user_id, gid, members, api_client, token)

                    # Mostrar visualización de agendas si está activa
                    if 'current_group_view' in st.session_state and st.session_state.current_group_view == gid:
                        show_group_agendas(user_id, gid, api_client, token)

                    # Mostrar disponibilidad común si está activa
                    if 'common_availability_group' in st.session_state and st.session_state.common_availability_group == gid:
                        show_common_availability(gid, api_client, token)

                    st.markdown("---")
                except Exception as e:
                    st.error(f"Error al cargar miembros del grupo: {str(e)}")
        else:
            st.info("No perteneces a ningún grupo")
    except Exception as e:
        st.error(f"Error al cargar grupos: {str(e)}")

def show_group_edit_panel(user_id, group_id, current_name, api_client, token):
    """Panel de edición para líderes del grupo"""
    st.markdown("---")
    st.subheader("✏️ Editar grupo")

    # Get current group info
    try:
        group_info = api_client.get_group_info(group_id, token)
        current_desc = group_info.get('description', '')
    except:
        current_desc = ""

    col1, col2 = st.columns(2)
    with col1:
        new_name = st.text_input("Nombre del grupo", value=current_name, key=f"edit_name_{group_id}")
    with col2:
        new_desc = st.text_area("Descripción", value=current_desc or "", key=f"edit_desc_{group_id}")

    col_save, col_cancel = st.columns(2)
    with col_save:
        if st.button("💾 Guardar cambios", key=f"save_{group_id}"):
            try:
                # Only send fields that have changed
                update_data = {}
                if new_name != current_name:
                    update_data['name'] = new_name
                if new_desc != current_desc:
                    update_data['description'] = new_desc
                
                if update_data:
                    result = api_client.update_group(group_id, token=token, **update_data)
                    st.success(result['message'])
                    st.session_state[f'editing_group_{group_id}'] = False
                    st.rerun()
                else:
                    st.info("No hay cambios para guardar")
            except Exception as e:
                st.error(f"Error al actualizar grupo: {str(e)}")

    with col_cancel:
        if st.button("❌ Cancelar", key=f"cancel_edit_{group_id}"):
            st.session_state[f'editing_group_{group_id}'] = False
            st.rerun()

def show_delete_group_confirmation(user_id, group_id, group_name, api_client, token):
    """Panel de confirmación de eliminación de grupo"""
    st.markdown("---")
    st.error("### ⚠️ Eliminar grupo")
    st.warning(f"Estás a punto de eliminar el grupo **{group_name}**")

    st.write("**Esta acción es irreversible y eliminará:**")
    st.write("- ❌ Todos los miembros del grupo")
    st.write("- ❌ Todas las invitaciones pendientes")
    st.write("- ❌ Todos los eventos del grupo")

    confirm_text = st.text_input(
        "Escribe 'ELIMINAR' para confirmar:",
        key=f"confirm_delete_{group_id}"
    )

    col_delete, col_cancel = st.columns(2)
    with col_delete:
        if st.button("🗑️ Eliminar permanentemente", key=f"confirm_delete_btn_{group_id}", type="primary"):
            if confirm_text == "ELIMINAR":
                try:
                    result = api_client.delete_group(group_id, token)
                    st.success(result['message'])
                    st.session_state[f'deleting_group_{group_id}'] = False
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al eliminar grupo: {str(e)}")
            else:
                st.error("❌ Debes escribir 'ELIMINAR' para confirmar")

    with col_cancel:
        if st.button("❌ Cancelar", key=f"cancel_delete_{group_id}"):
            st.session_state[f'deleting_group_{group_id}'] = False
            st.rerun()

def show_member_management(leader_id, group_id, member_details, api_client, token):
    """Panel de gestión de miembros para líderes"""
    st.markdown("**Invitar nuevos miembros**")

    # Obtener usuarios que no están en el grupo
    try:
        all_users = api_client.list_users(token)
        current_member_ids = [m[0] for m in member_details]
        available_users = {u[1]: u[0] for u in all_users if u[0] not in current_member_ids and u[0] != leader_id}

        if available_users:
            selected_user = st.selectbox(
                "Seleccionar usuario",
                options=list(available_users.keys()),
                key=f"invite_user_{group_id}"
            )

            if st.button("📧 Enviar invitación", key=f"send_invite_{group_id}"):
                try:
                    result = api_client.invite_user_to_group(
                        group_id,
                        available_users[selected_user],
                        token
                    )
                    st.success(f"✅ {result['message']}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al invitar usuario: {str(e)}")
        else:
            st.info("No hay usuarios disponibles para invitar")
    except Exception as e:
        st.error(f"Error al cargar usuarios: {str(e)}")

    st.markdown("---")
    st.markdown("**Eliminar miembros**")

    # Mostrar miembros que pueden ser eliminados (no líderes)
    # Note: We'll assume all members can be removed for now, except the leader
    removable_members = [(m[0], m[1]) for m in member_details if m[0] != leader_id]

    if removable_members:
        for member_id, username in removable_members:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"👤 {username}")
            with col2:
                if st.button("🗑️ Eliminar", key=f"remove_{group_id}_{member_id}"):
                    try:
                        result = api_client.remove_member(group_id, member_id, token)
                        st.success(result['message'])
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al eliminar miembro: {str(e)}")
    else:
        st.info("No hay miembros regulares para eliminar")

def show_group_agendas(viewer_id, group_id, api_client, token):
    """Mostrar agendas del grupo con control de acceso"""
    st.subheader("📊 Agendas del grupo")
    
    try:
        # Get group members
        members = api_client.list_group_members(group_id, token)
        
        if not members:
            st.info("No hay miembros en este grupo")
            return
            
        # Get events for each member
        all_events = []
        member_names = {}
        
        for member_id, member_name in members:
            member_names[member_id] = member_name
            try:
                # Get events for this member
                events = api_client.get_user_events_detailed(token, "all")
                # Filter events that are related to this group
                group_events = [e for e in events if e.get('group_id') == group_id]
                for event in group_events:
                    event['member_id'] = member_id
                    event['member_name'] = member_name
                    all_events.append(event)
            except Exception as e:
                st.warning(f"Error al cargar eventos para {member_name}: {str(e)}")
        
        if not all_events:
            st.info("No hay eventos en este grupo")
            return
            
        # Group events by date
        events_by_date = {}
        for event in all_events:
            try:
                date_key = event['start_time'].split(' ')[0]  # Extract date part
                if date_key not in events_by_date:
                    events_by_date[date_key] = []
                events_by_date[date_key].append(event)
            except:
                continue
        
        # Display events
        for date_key in sorted(events_by_date.keys()):
            st.markdown(f"### 📅 {date_key}")
            for event in events_by_date[date_key]:
                with st.expander(f"{event['title']} - {event['member_name']}"):
                    st.write(f"⏰ **{event['start_time']}** a **{event['end_time']}**")
                    if event['description']:
                        st.write(f"📝 {event['description']}")
                    st.write(f"👤 **Creador:** {event['creator_name']}")
    except Exception as e:
        st.error(f"Error al cargar agendas del grupo: {str(e)}")
    
    # Button to close the view
    if st.button("Cerrar agendas", key=f"close_agendas_{group_id}"):
        del st.session_state.current_group_view
        st.rerun()

def show_common_availability(group_id, api_client, token):
    """Mostrar horarios comunes disponibles"""
    st.subheader("🕐 Horarios comunes disponibles")
    
    try:
        # Get group members
        members = api_client.list_group_members(group_id, token)
        
        if not members:
            st.info("No hay miembros en este grupo para calcular disponibilidad")
            return
            
        # Get events for each member in the next week
        all_events = []
        member_names = {}
        
        # Calculate date range for next week
        today = datetime.now()
        next_week = today + timedelta(days=7)
        
        for member_id, member_name in members:
            member_names[member_id] = member_name
            try:
                # Get upcoming events for this member
                events = api_client.get_user_events_detailed(token, "upcoming")
                # Filter events for the next week
                week_events = [e for e in events if e.get('group_id') == group_id]
                for event in week_events:
                    try:
                        event_start = datetime.strptime(event['start_time'], '%Y-%m-%d %H:%M:%S')
                        if today <= event_start <= next_week:
                            event['member_id'] = member_id
                            all_events.append(event)
                    except:
                        continue
            except Exception as e:
                st.warning(f"Error al cargar eventos para {member_name}: {str(e)}")
        
        # Find common free slots (simplified approach)
        st.info("Búsqueda de disponibilidad común en desarrollo...")
        st.write("Los miembros del grupo:")
        for _, member_name in members:
            st.write(f"- 👤 {member_name}")
            
        if all_events:
            st.write("Próximos eventos:")
            for event in all_events[:5]:  # Show first 5 events
                st.write(f"- 📅 {event['title']} ({event['start_time']}) - {member_names.get(event.get('member_id', ''), 'Desconocido')}")
        else:
            st.write("No hay eventos programados en la próxima semana")
            
        # Suggest common time slots (simplified)
        st.subheader("Sugerencias de horarios comunes:")
        st.write("🕒 Mañana (9:00 - 12:00)")
        st.write("🕒 Tarde (14:00 - 17:00)")
        st.write("🕒 Noche (19:00 - 21:00)")
        
    except Exception as e:
        st.error(f"Error al calcular disponibilidad común: {str(e)}")
    
    # Button to close the view
    if st.button("Cerrar disponibilidad", key=f"close_availability_{group_id}"):
        del st.session_state.common_availability_group
        st.rerun()