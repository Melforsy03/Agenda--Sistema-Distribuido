from database.repository import Database
from websocket_manager import websocket_manager
from notification_service import NotificationService
from hierarchy_service import HierarchyService

class EventService:
    def __init__(self):
        self.db = Database()
        self.notifications = NotificationService()
        self.hierarchy = HierarchyService()

    async def create_event(self, title, description, start_time, end_time,
                         creator_id, group_id=None, is_group_event=False, 
                         participants_ids=None, is_hierarchical=False):
        """Crea un evento validando conflictos de horario con soporte para jerarquías."""
        
        # Lógica para eventos jerárquicos
        if is_hierarchical and group_id:
            return await self.hierarchy.create_hierarchical_event(
                title, description, start_time, end_time, creator_id, group_id
            )
        
        # Lógica original para eventos normales
        if self.db.check_conflict(creator_id, start_time, end_time):
            return None, "Conflicto en agenda del creador"

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

        # Notificaciones en tiempo real
        if group_id and is_group_event:
            await self.notifications.notify_group_event(event_id, group_id, creator_id)
        elif participants_ids:
            for user_id in participants_ids:
                if user_id != creator_id:
                    await websocket_manager.send_to_user(user_id, {
                        "type": "event_invitation",
                        "event_id": event_id,
                        "title": title,
                        "start_time": start_time,
                        "end_time": end_time
                    })

        return event_id, None

    # Mantener métodos existentes para compatibilidad
    def get_user_events(self, user_id):
        """Eventos de un usuario."""
        return self.db.get_events_by_user(user_id)

    def has_conflict(self, user_id, start_time, end_time):
        """Chequear conflictos en agenda de un usuario."""
        return self.db.check_conflict(user_id, start_time, end_time)
    
    async def update_event(self, event_id, user_id, **updates):
        """Actualizar evento con notificaciones (nuevo método)."""
        # Validar permisos
        self.db.cursor.execute('SELECT creator_id FROM events WHERE id = ?', (event_id,))
        event = self.db.cursor.fetchone()
        
        if not event or event[0] != user_id:
            return False, "No tienes permisos para modificar este evento"
        
        # Aquí iría la lógica de actualización en la base de datos
        # ...
        
        await self.notifications.notify_event_update(event_id, "updated")
        return True, "Evento actualizado"