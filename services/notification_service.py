from database.repository import Database
from websocket_manager import websocket_manager
from hierarchy_service import HierarchyService
import logging
from datetime import datetime

class NotificationService:
    def __init__(self):
        self.db = Database()
        self.hierarchy = HierarchyService()
    
    async def notify_group_event(self, event_id: int, group_id: int, creator_id: int):
        """Notificar a miembros del grupo sobre nuevo evento"""
        members = self.db.get_group_members(group_id)
        
        for member_id, username in members:
            if member_id != creator_id:
                await websocket_manager.send_to_user(member_id, {
                    "type": "group_event_invitation",
                    "event_id": event_id,
                    "group_id": group_id,
                    "timestamp": datetime.now().isoformat()
                })
    
    async def notify_event_update(self, event_id: int, update_type: str):
        """Notificar actualización de evento a participantes"""
        self.db.cursor.execute('''
            SELECT user_id FROM event_participants WHERE event_id = ?
        ''', (event_id,))
        
        participants = self.db.cursor.fetchall()
        
        for participant in participants:
            user_id = participant[0]
            await websocket_manager.send_to_user(user_id, {
                "type": f"event_{update_type}",
                "event_id": event_id,
                "timestamp": datetime.now().isoformat()
            })
    
    async def notify_hierarchical_event(self, group_id: int, event_title: str, 
                                      leader_id: int, affected_members: list):
        """Notificar sobre evento jerárquico aplicado"""
        leader_name = self.db.get_username(leader_id)
        
        for member_id in affected_members:
            await websocket_manager.send_to_user(member_id, {
                "type": "hierarchical_event_notification",
                "group_id": group_id,
                "event_title": event_title,
                "leader_name": leader_name,
                "timestamp": datetime.now().isoformat(),
                "message": f"El líder {leader_name} ha programado un evento obligatorio: {event_title}"
            })
    
    def get_user_notifications(self, user_id: int, limit: int = 20):
        """Obtener notificaciones recientes del usuario"""
        # Podría extenderse con una tabla de notificaciones persistente
        # Por ahora usamos notificaciones en tiempo real via WebSocket
        return []  # Placeholder para notificaciones persistentes futuras