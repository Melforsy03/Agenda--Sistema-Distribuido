import streamlit as st
from datetime import datetime
from services.event_service import EventService
from services.group_service import GroupService
from services.auth_service import AuthService
from services.hierarchy_service import HierarchyService
import asyncio

def show_create_event_view(user_id):
    st.header("➕ Crear evento")

    # Verificar si hay datos pre-llenados desde horarios disponibles
    prefill_start = st.session_state.pop('prefill_start', None)
    prefill_end = st.session_state.pop('prefill_end', None)
    prefill_group_id = st.session_state.pop('prefill_group_id', None)

    # Valores por defecto
    default_start_date = None
    default_start_time = None
    default_end_date = None
    default_end_time = None

    if prefill_start and prefill_end:
        try:
            start_dt = datetime.strptime(prefill_start, '%Y-%m-%d %H:%M:%S')
            end_dt = datetime.strptime(prefill_end, '%Y-%m-%d %H:%M:%S')
            default_start_date = start_dt.date()
            default_start_time = start_dt.time()
            default_end_date = end_dt.date()
            default_end_time = end_dt.time()
            st.info(f"📅 Horario seleccionado: {prefill_start} ➡️ {prefill_end}")
        except ValueError:
            pass

    title = st.text_input("Título")
    description = st.text_area("Descripción")

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Fecha inicio", value=default_start_date)
        start_time = st.time_input("Hora inicio", value=default_start_time)
    with col2:
        end_date = st.date_input("Fecha fin", value=default_end_date)
        end_time = st.time_input("Hora fin", value=default_end_time)

    start_str = f"{start_date} {start_time}"
    end_str = f"{end_date} {end_time}"

    is_group_event = st.checkbox("Evento grupal", value=prefill_group_id is not None)

    # NUEVO: Opción para evento jerárquico
    is_hierarchical = False
    participants_ids = []
    group_id = None

    if is_group_event:
        groups = GroupService().list_user_groups(user_id)
        if groups:
            group_names = [g[1] for g in groups]

            # Pre-seleccionar grupo si viene de horarios disponibles
            default_index = 0
            if prefill_group_id:
                try:
                    default_index = [g[0] for g in groups].index(prefill_group_id)
                except ValueError:
                    pass

            selected_group_name = st.selectbox("Selecciona grupo", group_names, index=default_index)
            group_id = [g[0] for g in groups if g[1] == selected_group_name][0]
            
            # Verificar si el usuario es líder para permitir eventos jerárquicos
            hierarchy_service = HierarchyService()
            user_role = hierarchy_service.get_user_role_in_group(user_id, group_id)
            
            if user_role == "leader":
                is_hierarchical = st.checkbox("Evento jerárquico (obligatorio para todos los miembros)")
            
            members = GroupService().list_group_members(group_id)
            participants_ids = [m[0] for m in members]
            
            st.info(f"Participantes: {', '.join([m[1] for m in members])}")
            if is_hierarchical:
                st.warning("⚠️ Este evento se aplicará automáticamente a todos los miembros del grupo")
        else:
            st.warning("No tienes grupos")
    else:
        users = AuthService().list_users()
        options = {u[1]: u[0] for u in users if u[0] != user_id}
        selected = st.multiselect("Invitar usuarios", list(options.keys()))
        participants_ids = [options[s] for s in selected]

    if st.button("Crear evento"):
        try:
            datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S')
            datetime.strptime(end_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            st.error("Formato de fecha/hora inválido")
            return

        # NUEVO: Usar función asíncrona
        async def create_event_async():
            return await EventService().create_event(
                title, description, start_str, end_str,
                user_id, group_id, is_group_event, 
                participants_ids, is_hierarchical
            )
        
        # Ejecutar la función asíncrona
        event_id, error = asyncio.run(create_event_async())
        
        if event_id:
            st.success("✅ Evento creado")
            if is_hierarchical:
                st.success("🔔 Notificaciones enviadas a todos los miembros del grupo")
            st.balloons()
            st.rerun()
        else:
            st.error(f"❌ {error}")