import streamlit as st
from streamlit_calendar import calendar
import asyncio
from datetime import datetime

def show_calendar_view(user_id, api_client, token):
    st.header("📅 Mi calendario")

    # Solo mostrar la vista de calendario
    try:
        events = api_client.get_user_events(token)
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
    except Exception as e:
        st.error(f"Error al cargar eventos: {str(e)}")
