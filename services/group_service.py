from database.repository import Database

class GroupService:
    def __init__(self):
        self.db = Database()

    def create_group(self, name, description, is_hierarchical, creator_id, members=None):
        """Crear grupo y enviar invitaciones."""
        group_id = self.db.add_group(name, description, is_hierarchical, creator_id)
        if not group_id:
            return None, "El grupo ya existe"

        invited = 0
        if members:
            for m in members:
                if self.db.invite_user_to_group(group_id, m, creator_id):
                    invited += 1
        return group_id, invited

    def list_user_groups(self, user_id):
        return self.db.get_groups_by_user(user_id)

    def list_group_members(self, group_id):
        return self.db.get_group_members(group_id)

    def invite_user(self, group_id, invited_user_id, inviter_id):
        return self.db.invite_user_to_group(group_id, invited_user_id, inviter_id)

    def pending_invitations(self, user_id):
        return self.db.get_pending_invitations(user_id)

    def respond_invitation(self, invitation_id, response, user_id):
        return self.db.respond_to_invitation(invitation_id, response, user_id)
