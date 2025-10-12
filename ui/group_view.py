import streamlit as st
from services.group_service import GroupService
from services.auth_service import AuthService
#from services.visualization_service import VisualizationService
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
            
            group_id, invited = asyncio.run(create_group_async())
            if group_id:
                st.success(f"✅ Grupo creado (invitaciones enviadas: {invited})")
                st.rerun()
            else:
                st.error("❌ Ese grupo ya existe")

    # --- Listar grupos con nuevas funcionalidades ---
    groups = GroupService().list_user_groups(user_id)
    if groups:
        for g in groups:
            gid, gname, hier = g
            st.subheader(f"🏢 {gname} {'👑 (Jerárquico)' if hier else '👥 (No jerárquico)'}")
            
            # NUEVO: Visualización de agendas del grupo
            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"📊 Ver agendas del grupo", key=f"view_{gid}"):
                    st.session_state.current_group_view = gid
            
            with col2:
                if st.button(f"🕐 Disponibilidad común", key=f"availability_{gid}"):
                    st.session_state.common_availability_group = gid
            
            # Mostrar miembros con sus roles
            members = GroupService().list_group_members(gid)
            hierarchy_service = HierarchyService()
            
            leaders = []
            regular_members = []
            
            for member_id, username in members:
                role = hierarchy_service.get_user_role_in_group(member_id, gid)
                if role == "leader":
                    leaders.append(username)
                else:
                    regular_members.append(username)
            
            st.write("**Líderes:** " + ", ".join([f"👑 {l}" for l in leaders]))
            st.write("**Miembros:** " + ", ".join(regular_members))
            
            # NUEVO: Mostrar visualización de agendas si está activa
            if hasattr(st.session_state, 'current_group_view') and st.session_state.current_group_view == gid:
                show_group_agendas(user_id, gid)
            
            # NUEVO: Mostrar disponibilidad común si está activa
            if hasattr(st.session_state, 'common_availability_group') and st.session_state.common_availability_group == gid:
                show_common_availability(gid)
                
            st.markdown("---")
    else:
        st.info("No perteneces a ningún grupo")

def show_group_agendas(viewer_id, group_id):
    """NUEVO: Mostrar agendas del grupo con control de acceso"""
    st.subheader("📊 Agendas del grupo")
    
    date_col1, date_col2 = st.columns(2)
    with date_col1:
        start_date = st.date_input("Fecha inicio", key=f"start_{group_id}")
    with date_col2:
        end_date = st.date_input("Fecha fin", key=f"end_{group_id}")
    
    # if st.button("Cargar agendas"):
    #     viz_service = VisualizationService()
    #     group_agendas, error = viz_service.get_group_agendas(
    #         viewer_id, group_id, 
    #         start_date.strftime('%Y-%m-%d'), 
    #         end_date.strftime('%Y-%m-%d')
    #     )
        
    #     if error:
    #         st.error(f"❌ {error}")
    #     else:
    #         for username, user_data in group_agendas.items():
    #             with st.expander(f"📅 Agenda de {username}"):
    #                 events = user_data["events"]
    #                 if events:
    #                     for event in events:
    #                         st.write(f"**{event['title']}**")
    #                         st.write(f"🕐 {event['start_time']} - {event['end_time']}")
    #                         st.write(f"📝 {event['description']}")
    #                 else:
    #                     st.info("No hay eventos en este período")

def show_common_availability(group_id):
    """NUEVO: Mostrar horarios comunes disponibles"""
    st.subheader("🕐 Horarios comunes disponibles")
    
    date_col1, date_col2 = st.columns(2)
    with date_col1:
        start_date = st.date_input("Fecha inicio", key=f"avail_start_{group_id}")
    with date_col2:
        end_date = st.date_input("Fecha fin", key=f"avail_end_{group_id}")
    
    duration = st.slider("Duración requerida (horas)", 1, 8, 2)
    
    # if st.button("Buscar horarios disponibles"):
    #     viz_service = VisualizationService()
    #     available_slots = viz_service.get_common_availability(
    #         group_id,
    #         start_date.strftime('%Y-%m-%d'),
    #         end_date.strftime('%Y-%m-%d'),
    #         duration
    #     )
        
    #     if available_slots:
    #         st.success(f"✅ Encontrados {len(available_slots)} horarios disponibles")
    #         for slot in available_slots[:10]:  # Mostrar máximo 10
    #             st.write(f"📅 {slot['start_time']} - {slot['end_time']}")
    #     else:
    #         st.warning("❌ No hay horarios comunes disponibles en este período")