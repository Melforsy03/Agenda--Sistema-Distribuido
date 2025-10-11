from database.repository import Database
from websocket_manager import websocket_manager
import asyncio

class GroupService:
    def __init__(self):
        self.db = Database()

    async def create_group(self, name, description, is_hierarchical, creator_id, members=None):
        """Crear grupo y enviar invitaciones con notificaciones."""
        group_id = self.db.add_group(name, description, is_hierarchical, creator_id)
        if not group_id:
            return None, "El grupo ya existe"

        invited = 0
        if members:
            for m in members:
                if self.db.invite_user_to_group(group_id, m, creator_id):
                    invited += 1
                    # Notificar al usuario invitado
                    await websocket_manager.send_to_user(m, {
                        "type": "group_invitation",
                        "group_id": group_id,
                        "group_name": name,
                        "inviter_id": creator_id
                    })
        return group_id, invited

    # Mantener métodos existentes...
    def list_user_groups(self, user_id):
        return self.db.get_groups_by_user(user_id)

    def list_group_members(self, group_id):
        return self.db.get_group_members(group_id)

    async def invite_user(self, group_id, invited_user_id, inviter_id):
        success = self.db.invite_user_to_group(group_id, invited_user_id, inviter_id)
        if success:
            group_name = self.db.cursor.execute(
                'SELECT name FROM groups WHERE id = ?', (group_id,)
            ).fetchone()[0]
            
            await websocket_manager.send_to_user(invited_user_id, {
                "type": "group_invitation",
                "group_id": group_id,
                "group_name": group_name,
                "inviter_id": inviter_id
            })
        return success

    def pending_invitations(self, user_id):
        return self.db.get_pending_invitations(user_id)

    async def respond_invitation(self, invitation_id, response, user_id):
        success = self.db.respond_to_invitation(invitation_id, response, user_id)
        if success and response == 'accepted':
            # Notificar al grupo sobre nuevo miembro
            invitation = self.db.cursor.execute(
                'SELECT group_id FROM group_invitations WHERE id = ?', (invitation_id,)
            ).fetchone()
            if invitation:
                group_members = self.db.get_group_members(invitation[0])
                for member_id, _ in group_members:
                    if member_id != user_id:
                        await websocket_manager.send_to_user(member_id, {
                            "type": "new_group_member",
                            "group_id": invitation[0],
                            "new_member_id": user_id
                        })
        return success