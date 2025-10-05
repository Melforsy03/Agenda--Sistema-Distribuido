import streamlit as st
from streamlit_calendar import calendar
from services.event_service import EventService

def show_calendar_view(user_id):
    st.header("📅 Mi calendario")

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
