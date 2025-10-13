import streamlit as st
from streamlit_calendar import calendar
from services.event_service import EventService
import asyncio
from datetime import datetime

def show_calendar_view(user_id):
    st.header("📅 Mi calendario")

    # Tabs para vista de calendario y lista de eventos
    tab1, tab2 = st.tabs(["📅 Vista Calendario", "📋 Lista de Eventos"])

    with tab1:
        show_calendar_tab(user_id)

    with tab2:
        show_events_list_tab(user_id)


def show_calendar_tab(user_id):
    """Vista de calendario tradicional"""
    events = EventService().get_user_events(user_id)
    calendar_events = []
    for e in events:
        calendar_events.append({
            "title": e[0],
            "start": e[2],
            "end": e[3],
        })

    calendar_options = {
        "headerToolbar": {
            "left": "today prev,next",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek,timeGridDay",
        },
        "initialView": "dayGridMonth"
    }

    calendar(events=calendar_events, options=calendar_options, key="calendar1")


def show_events_list_tab(user_id):
    """Vista de lista de eventos con filtros y detalles"""
    event_service = EventService()

    # Filtros
    st.subheader("🔍 Filtrar eventos")
    col1, col2 = st.columns(2)

    with col1:
        filter_type = st.selectbox(
            "Mostrar:",
            ["Todos", "Próximos", "Pasados", "Pendientes de aceptar", "Creados por mí"],
            key="event_filter"
        )

    with col2:
        search_text = st.text_input("🔎 Buscar por título", key="search_text")

    # Mapear filtro seleccionado
    filter_map = {
        "Todos": "all",
        "Próximos": "upcoming",
        "Pasados": "past",
        "Pendientes de aceptar": "pending",
        "Creados por mí": "created"
    }

    # Obtener eventos filtrados
    events = event_service.get_user_events_detailed(user_id, filter_map[filter_type])

    # Aplicar búsqueda por texto
    if search_text:
        events = [e for e in events if search_text.lower() in e['title'].lower()]

    # Mostrar estadísticas
    st.markdown("---")
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    with col_stat1:
        st.metric("Total eventos", len(events))
    with col_stat2:
        pending_count = len([e for e in events if e['is_accepted'] == 0 and not e['is_creator']])
        st.metric("Pendientes", pending_count)
    with col_stat3:
        created_count = len([e for e in events if e['is_creator']])
        st.metric("Creados por ti", created_count)

    st.markdown("---")

    # Mostrar lista de eventos
    if not events:
        st.info("No hay eventos para mostrar con los filtros seleccionados")
    else:
        for event in events:
            show_event_card(event, user_id, event_service)


def show_event_card(event, user_id, event_service):
    """Mostrar tarjeta de evento con detalles y acciones"""
    # Determinar el estado del evento
    try:
        event_date = datetime.strptime(event['start_time'], '%Y-%m-%d %H:%M:%S')
        is_past = event_date < datetime.now()
    except:
        is_past = False

    # Determinar el color/estado del evento
    if event['is_creator']:
        status_badge = "🔵 Creado por ti"
        status_color = "blue"
    elif event['is_accepted'] == 0:
        status_badge = "🟡 Pendiente de aceptar"
        status_color = "orange"
    elif is_past:
        status_badge = "🔴 Evento pasado"
        status_color = "red"
    else:
        status_badge = "🟢 Confirmado"
        status_color = "green"

    # Contenedor del evento
    with st.container():
        # Header del evento
        col_title, col_status = st.columns([3, 1])
        with col_title:
            st.markdown(f"### {event['title']}")
        with col_status:
            st.markdown(f"**{status_badge}**")

        # Información básica
        col_info1, col_info2 = st.columns(2)
        with col_info1:
            st.write(f"📅 **Inicio:** {event['start_time']}")
            st.write(f"⏰ **Fin:** {event['end_time']}")
        with col_info2:
            st.write(f"👤 **Creador:** {event['creator_name']}")
            if event['is_group_event'] and event['group_name']:
                st.write(f"👥 **Grupo:** {event['group_name']}")

        # Descripción
        if event['description']:
            with st.expander("📝 Ver descripción"):
                st.write(event['description'])

        # Botón para ver detalles completos
        col_actions1, col_actions2, col_actions3 = st.columns(3)

        with col_actions1:
            if st.button(f"ℹ️ Ver detalles", key=f"details_{event['id']}"):
                st.session_state[f'show_details_{event["id"]}'] = True

        # Acciones según el rol del usuario
        if event['is_creator']:
            with col_actions2:
                if st.button(f"❌ Cancelar evento", key=f"cancel_{event['id']}"):
                    st.session_state[f'confirm_cancel_{event["id"]}'] = True

            # Confirmación de cancelación
            if st.session_state.get(f'confirm_cancel_{event["id"]}', False):
                st.warning("⚠️ ¿Estás seguro de que quieres cancelar este evento?")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("Sí, cancelar", key=f"yes_cancel_{event['id']}"):
                        async def cancel():
                            return await event_service.cancel_event(event['id'], user_id)
                        success, message = asyncio.run(cancel())
                        if success:
                            st.success(f"✅ {message}")
                            st.session_state[f'confirm_cancel_{event["id"]}'] = False
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
                with col_no:
                    if st.button("No, mantener", key=f"no_cancel_{event['id']}"):
                        st.session_state[f'confirm_cancel_{event["id"]}'] = False
                        st.rerun()

        else:
            # Participante puede salir del evento
            with col_actions2:
                if st.button(f"🚪 Salir del evento", key=f"leave_{event['id']}"):
                    st.session_state[f'confirm_leave_{event["id"]}'] = True

            # Confirmación de salida
            if st.session_state.get(f'confirm_leave_{event["id"]}', False):
                st.warning("⚠️ ¿Estás seguro de que quieres salir de este evento?")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("Sí, salir", key=f"yes_leave_{event['id']}"):
                        async def leave():
                            return await event_service.leave_event(event['id'], user_id)
                        success, message = asyncio.run(leave())
                        if success:
                            st.success(f"✅ {message}")
                            st.session_state[f'confirm_leave_{event["id"]}'] = False
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
                with col_no:
                    if st.button("No, quedarme", key=f"no_leave_{event['id']}"):
                        st.session_state[f'confirm_leave_{event["id"]}'] = False
                        st.rerun()

        # Mostrar detalles completos si se solicita
        if st.session_state.get(f'show_details_{event["id"]}', False):
            show_event_details(event['id'], user_id, event_service)

        st.markdown("---")


def show_event_details(event_id, user_id, event_service):
    """Mostrar detalles completos del evento incluyendo participantes"""
    details, error = event_service.get_event_details(event_id, user_id)

    if error:
        st.error(f"❌ {error}")
        return

    with st.expander("📊 Detalles completos del evento", expanded=True):
        st.markdown(f"### {details['title']}")

        # Información completa
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**📅 Inicio:** {details['start_time']}")
            st.write(f"**⏰ Fin:** {details['end_time']}")
            st.write(f"**👤 Creador:** {details['creator_name']}")
        with col2:
            if details['is_group_event']:
                st.write(f"**👥 Grupo:** {details['group_name']}")
                if details['is_hierarchical']:
                    st.write("**👑 Evento jerárquico**")

        if details['description']:
            st.markdown("**📝 Descripción:**")
            st.write(details['description'])

        # Lista de participantes
        st.markdown("---")
        st.markdown("### 👥 Participantes")

        if details['participants']:
            accepted = [p for p in details['participants'] if p['is_accepted']]
            pending = [p for p in details['participants'] if not p['is_accepted']]

            col_accepted, col_pending = st.columns(2)

            with col_accepted:
                st.markdown(f"**✅ Confirmados ({len(accepted)})**")
                for p in accepted:
                    st.write(f"• {p['username']}")

            with col_pending:
                st.markdown(f"**⏳ Pendientes ({len(pending)})**")
                for p in pending:
                    st.write(f"• {p['username']}")
        else:
            st.info("No hay participantes en este evento")

        # Botón para cerrar detalles
        if st.button("Cerrar detalles", key=f"close_details_{event_id}"):
            st.session_state[f'show_details_{event_id}'] = False
            st.rerun()
