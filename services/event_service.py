from database.repository import Database

class EventService:
    def __init__(self):
        self.db = Database()

    def create_event(self, title, description, start_time, end_time,
                     creator_id, group_id=None, is_group_event=False, participants_ids=None):
        """Crea un evento validando conflictos de horario."""
        if self.db.check_conflict(creator_id, start_time, end_time):
            return None, f"Conflicto en agenda del creador"

        # Chequear conflictos de los invitados
        if participants_ids:
            conflict_users = [p for p in participants_ids if self.db.check_conflict(p, start_time, end_time)]
            if conflict_users:
                return None, f"Conflicto con participantes: {conflict_users}"

        event_id = self.db.add_event(title, description, start_time, end_time,
                                     creator_id, group_id, is_group_event)

        # Añadir participantes (incluye al creador)
        all_participants = set(participants_ids or []) | {creator_id}
        for p in all_participants:
            self.db.add_participant_to_event(event_id, p)

        return event_id, None

    def get_user_events(self, user_id):
        """Eventos de un usuario."""
        return self.db.get_events_by_user(user_id)

    def has_conflict(self, user_id, start_time, end_time):
        """Chequear conflictos en agenda de un usuario."""
        return self.db.check_conflict(user_id, start_time, end_time)
