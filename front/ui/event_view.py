import streamlit as st
from datetime import datetime
import asyncio

def show_create_event_view(user_id, api_client, token):
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
        try:
            groups = api_client.list_user_groups(token)
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
                
                # Note: Hierarchy service functionality would need to be implemented in the API
                # For now, we'll skip the hierarchical option
                members = api_client.list_group_members(group_id, token)
                participants_ids = [m[0] for m in members]
                
                st.info(f"Participantes: {', '.join([m[1] for m in members])}")
            else:
                st.warning("No tienes grupos")
        except Exception as e:
            st.error(f"Error al cargar grupos: {str(e)}")
    else:
        try:
            users = api_client.list_users(token)
            options = {u[1]: u[0] for u in users if u[0] != user_id}
            selected = st.multiselect("Invitar usuarios", list(options.keys()))
            participants_ids = [options[s] for s in selected]
        except Exception as e:
            st.error(f"Error al cargar usuarios: {str(e)}")

    if st.button("Crear evento"):
        try:
            datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S')
            datetime.strptime(end_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            st.error("Formato de fecha/hora inválido")
            return

        try:
            # Create event using API
            result = api_client.create_event(
                title, description, start_str, end_str,
                token, group_id, is_group_event, 
                participants_ids, is_hierarchical
            )
            
            st.success("✅ Evento creado")
            if is_hierarchical:
                st.success("🔔 Notificaciones enviadas a todos los miembros del grupo")
            st.balloons()
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error al crear evento: {str(e)}")