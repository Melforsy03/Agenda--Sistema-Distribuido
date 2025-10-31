from database.repository import Database
from services.websocket_manager import websocket_manager
from services.notification_service import NotificationService
from services.hierarchy_service import HierarchyService

class EventService:
    def __init__(self):
        self.db = Database()
        self.notifications = NotificationService()
        self.hierarchy = HierarchyService()

    async def create_event(self, title, description, start_time, end_time,
                         creator_id, group_id=None, is_group_event=False,
                         participants_ids=None, is_hierarchical=False):
        """Crea un evento validando conflictos de horario con soporte para jerarquías."""
        
        # Validar campos requeridos
        if not title:
            return None, "El título es requerido"
        
        if not start_time:
            return None, "La fecha y hora de inicio son requeridas"
            
        if not end_time:
            return None, "La fecha y hora de fin son requeridas"
            
        if not creator_id:
            return None, "El creador del evento es requerido"

        # Validar que la fecha de inicio sea anterior a la fecha de fin
        from datetime import datetime
        try:
            start_dt = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
            end_dt = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
            if start_dt >= end_dt:
                return None, "La fecha y hora de inicio debe ser anterior a la fecha y hora de finalización"
        except ValueError as e:
            return None, f"Formato de fecha inválido: {str(e)}"

        # Lógica para eventos jerárquicos
        if is_hierarchical and group_id:
            return await self.hierarchy.create_hierarchical_event(
                title, description, start_time, end_time, creator_id, group_id
            )

        # Lógica original para eventos normales
        try:
            if self.db.check_conflict(creator_id, start_time, end_time):
                return None, "Conflicto en agenda del creador"
        except Exception as e:
            return None, f"Error al verificar conflictos del creador: {str(e)}"

        if participants_ids:
            try:
                conflict_users = [p for p in participants_ids if self.db.check_conflict(p, start_time, end_time)]
                if conflict_users:
                    return None, f"Conflicto con participantes: {conflict_users}"
            except Exception as e:
                return None, f"Error al verificar conflictos de participantes: {str(e)}"

        try:
            event_id = self.db.add_event(title, description, start_time, end_time,
                                       creator_id, group_id, is_group_event)
        except Exception as e:
            return None, f"Error al crear el evento en la base de datos: {str(e)}"

        # Añadir participantes
        # Creador siempre aceptado automáticamente
        try:
            self.db.add_participant_to_event(event_id, creator_id, is_accepted=True)
        except Exception as e:
            return None, f"Error al añadir al creador como participante: {str(e)}"

        # Verificar si el creador es líder del grupo
        is_leader = False
        if group_id:
            is_leader = self.db.is_group_leader(creator_id, group_id)

        # Para eventos de grupo NO jerárquicos, los participantes deben aceptar
        # Para eventos individuales, también requieren aceptación
        # Si el creador es líder, añadir automáticamente a todos los miembros sin notificación
        if participants_ids and not is_leader:
            try:
                for p in participants_ids:
                    if p != creator_id:
                        # En grupos no jerárquicos, requieren aceptación
                        self.db.add_participant_to_event(event_id, p, is_accepted=False)
            except Exception as e:
                return None, f"Error al añadir participantes: {str(e)}"
        elif group_id and is_group_event and is_leader:
            # Si es líder, añadir automáticamente a todos los miembros del grupo
            try:
                members = self.db.get_group_members(group_id)
                for member_id, username in members:
                    if member_id != creator_id:
                        self.db.add_participant_to_event(event_id, member_id, is_accepted=True)
            except Exception as e:
                return None, f"Error al añadir miembros del grupo automáticamente: {str(e)}"

        # Notificaciones en tiempo real
        try:
            # Solo enviar notificaciones si NO es un líder creando un evento grupal
            if not (group_id and is_group_event and is_leader):
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
        except Exception as e:
            # Log the error but don't fail the event creation
            print(f"Error al enviar notificaciones: {str(e)}")

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

    def get_pending_event_invitations(self, user_id):
        """Obtener invitaciones pendientes a eventos para un usuario."""
        self.db.cursor.execute('''
            SELECT e.id, e.title, e.description, e.start_time, e.end_time,
                   u.username as creator_name, g.name as group_name,
                   e.is_group_event, e.group_id
            FROM events e
            JOIN event_participants ep ON e.id = ep.event_id
            JOIN users u ON e.creator_id = u.id
            LEFT JOIN groups g ON e.group_id = g.id
            WHERE ep.user_id = ? AND ep.is_accepted = 0
            ORDER BY e.start_time
        ''', (user_id,))
        return self.db.cursor.fetchall()

    async def respond_to_event_invitation(self, event_id, user_id, accepted):
        """Aceptar o rechazar una invitación a un evento."""
        if accepted:
            # Verificar conflictos antes de aceptar
            self.db.cursor.execute(
                'SELECT start_time, end_time FROM events WHERE id = ?',
                (event_id,)
            )
            event = self.db.cursor.fetchone()

            if event and self.db.check_conflict(user_id, event[0], event[1]):
                return False, "Conflicto con otro evento en tu agenda"

            # Aceptar la invitación
            self.db.cursor.execute('''
                UPDATE event_participants
                SET is_accepted = 1
                WHERE event_id = ? AND user_id = ?
            ''', (event_id, user_id))
            self.db.conn.commit()

            # Notificar al creador
            self.db.cursor.execute('SELECT creator_id, title FROM events WHERE id = ?', (event_id,))
            event_data = self.db.cursor.fetchone()
            if event_data:
                creator_id, title = event_data
                username = self.db.get_username(user_id)
                await websocket_manager.send_to_user(creator_id, {
                    "type": "event_accepted",
                    "event_id": event_id,
                    "event_title": title,
                    "user_name": username
                })

            return True, "Invitación aceptada"
        else:
            # Rechazar la invitación (eliminar participante)
            self.db.cursor.execute('''
                DELETE FROM event_participants
                WHERE event_id = ? AND user_id = ?
            ''', (event_id, user_id))
            self.db.conn.commit()

            # Notificar al creador
            self.db.cursor.execute('SELECT creator_id, title FROM events WHERE id = ?', (event_id,))
            event_data = self.db.cursor.fetchone()
            if event_data:
                creator_id, title = event_data
                username = self.db.get_username(user_id)
                await websocket_manager.send_to_user(creator_id, {
                    "type": "event_declined",
                    "event_id": event_id,
                    "event_title": title,
                    "user_name": username
                })

            return True, "Invitación rechazada"

    def get_event_details(self, event_id, user_id):
        """Obtener detalles completos de un evento con participantes."""
        # Verificar que el usuario tenga acceso al evento
        self.db.cursor.execute('''
            SELECT 1 FROM event_participants
            WHERE event_id = ? AND user_id = ?
            UNION
            SELECT 1 FROM events
            WHERE id = ? AND creator_id = ?
        ''', (event_id, user_id, event_id, user_id))

        if not self.db.cursor.fetchone():
            return None, "No tienes acceso a este evento"

        # Obtener información del evento
        self.db.cursor.execute('''
            SELECT e.id, e.title, e.description, e.start_time, e.end_time,
                   e.creator_id, u.username as creator_name,
                   e.group_id, g.name as group_name, g.is_hierarchical,
                   e.is_group_event
            FROM events e
            JOIN users u ON e.creator_id = u.id
            LEFT JOIN groups g ON e.group_id = g.id
            WHERE e.id = ?
        ''', (event_id,))

        event_data = self.db.cursor.fetchone()
        if not event_data:
            return None, "Evento no encontrado"

        # Obtener participantes
        self.db.cursor.execute('''
            SELECT u.id, u.username, ep.is_accepted
            FROM event_participants ep
            JOIN users u ON ep.user_id = u.id
            WHERE ep.event_id = ?
            ORDER BY ep.is_accepted DESC, u.username
        ''', (event_id,))

        participants = []
        for p in self.db.cursor.fetchall():
            participants.append({
                'user_id': p[0],
                'username': p[1],
                'is_accepted': p[2]
            })

        event_details = {
            'id': event_data[0],
            'title': event_data[1],
            'description': event_data[2],
            'start_time': event_data[3],
            'end_time': event_data[4],
            'creator_id': event_data[5],
            'creator_name': event_data[6],
            'group_id': event_data[7],
            'group_name': event_data[8],
            'is_hierarchical': event_data[9],
            'is_group_event': event_data[10],
            'participants': participants
        }

        return event_details, None

    def get_user_events_detailed(self, user_id, filter_type='all'):
        """
        Obtener eventos del usuario con información detallada.
        filter_type: 'all', 'upcoming', 'past', 'pending', 'created'
        """
        from datetime import datetime

        base_query = '''
            SELECT e.id, e.title, e.description, e.start_time, e.end_time,
                   e.creator_id, u.username as creator_name,
                   g.name as group_name, e.is_group_event,
                   ep.is_accepted,
                   CASE WHEN e.creator_id = ? THEN 1 ELSE 0 END as is_creator
            FROM events e
            LEFT JOIN event_participants ep ON e.id = ep.event_id AND ep.user_id = ?
            LEFT JOIN users u ON e.creator_id = u.id
            LEFT JOIN groups g ON e.group_id = g.id
            WHERE (ep.user_id = ? OR e.creator_id = ?)
        '''

        params = [user_id, user_id, user_id, user_id]

        # Aplicar filtros
        if filter_type == 'upcoming':
            base_query += " AND datetime(e.start_time) >= datetime('now')"
        elif filter_type == 'past':
            base_query += " AND datetime(e.start_time) < datetime('now')"
        elif filter_type == 'pending':
            base_query += " AND ep.is_accepted = 0 AND e.creator_id != ?"
            params.append(user_id)
        elif filter_type == 'created':
            base_query += " AND e.creator_id = ?"
            params.append(user_id)

        base_query += " ORDER BY e.start_time DESC"

        self.db.cursor.execute(base_query, params)

        events = []
        for row in self.db.cursor.fetchall():
            events.append({
                'id': row[0],
                'title': row[1],
                'description': row[2],
                'start_time': row[3],
                'end_time': row[4],
                'creator_id': row[5],
                'creator_name': row[6],
                'group_name': row[7],
                'is_group_event': row[8],
                'is_accepted': row[9],
                'is_creator': row[10]
            })

        return events

    async def cancel_event(self, event_id, user_id):
        """Cancelar un evento (solo el creador puede hacerlo)."""
        # Verificar que el usuario es el creador
        self.db.cursor.execute(
            'SELECT creator_id, title FROM events WHERE id = ?',
            (event_id,)
        )
        event = self.db.cursor.fetchone()

        if not event:
            return False, "Evento no encontrado"

        if event[0] != user_id:
            return False, "Solo el creador puede cancelar el evento"

        # Obtener participantes antes de eliminar
        self.db.cursor.execute(
            'SELECT user_id FROM event_participants WHERE event_id = ?',
            (event_id,)
        )
        participants = [p[0] for p in self.db.cursor.fetchall()]

        # Eliminar participantes
        self.db.cursor.execute(
            'DELETE FROM event_participants WHERE event_id = ?',
            (event_id,)
        )

        # Eliminar evento
        self.db.cursor.execute('DELETE FROM events WHERE id = ?', (event_id,))
        self.db.conn.commit()

        # Notificar a participantes
        for participant_id in participants:
            if participant_id != user_id:
                await websocket_manager.send_to_user(participant_id, {
                    "type": "event_cancelled",
                    "event_id": event_id,
                    "event_title": event[1]
                })

        return True, "Evento cancelado exitosamente"

    async def leave_event(self, event_id, user_id):
        """Salir de un evento (solo para participantes, no creadores)."""
        # Verificar que el usuario no es el creador
        self.db.cursor.execute(
            'SELECT creator_id, title FROM events WHERE id = ?',
            (event_id,)
        )
        event = self.db.cursor.fetchone()

        if not event:
            return False, "Evento no encontrado"

        if event[0] == user_id:
            return False, "El creador no puede salir del evento. Usa 'Cancelar evento' en su lugar."

        # Eliminar participante
        self.db.cursor.execute(
            'DELETE FROM event_participants WHERE event_id = ? AND user_id = ?',
            (event_id, user_id)
        )
        self.db.conn.commit()

        # Notificar al creador
        username = self.db.get_username(user_id)
        await websocket_manager.send_to_user(event[0], {
            "type": "participant_left",
            "event_id": event_id,
            "event_title": event[1],
            "user_name": username
        })

        return True, "Has salido del evento"

    def get_pending_invitations_count(self, user_id):
        """Obtener conteo de invitaciones a eventos pendientes."""
        invitations = self.get_pending_event_invitations(user_id)
        return len(invitations) if invitations else 0