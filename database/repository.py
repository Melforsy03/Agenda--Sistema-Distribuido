import sqlite3
import bcrypt
from datetime import datetime
from .schema import setup_database
import os

class Database:
    def __init__(self, db_name='agenda.db'):
        setup_database(db_name)
        self.db_name = db_name
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()

    def close(self):
        self.conn.close()

    # ---------- Usuarios ----------
    def get_user(self, username):
        self.cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        return self.cursor.fetchone()

    def add_user(self, username, password):
        try:
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            self.cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, password_hash))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def check_password(self, username, password):
        user = self.get_user(username)
        if user:
            try:
                stored_hash = user[2]
                # Asegurarse de que el hash esté en bytes
                if isinstance(stored_hash, str):
                    stored_hash = stored_hash.encode('utf-8')

                # Asegurarse de que la contraseña esté en bytes
                if isinstance(password, str):
                    password = password.encode('utf-8')

                return bcrypt.checkpw(password, stored_hash)
            except Exception as e:
                print(f"Error al verificar contraseña: {e}")
                return False
        return False

    def get_user_id(self, username):
        self.cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def get_username(self, user_id):
        self.cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def get_all_users(self):
        self.cursor.execute('SELECT id, username FROM users')
        return self.cursor.fetchall()

    # ---------- Eventos ----------
    def add_event(self, title, description, start_time, end_time, creator_id, group_id=None, is_group_event=False):
        self.cursor.execute('''
            INSERT INTO events (title, description, start_time, end_time, creator_id, group_id, is_group_event)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (title, description, start_time, end_time, creator_id, group_id, is_group_event))
        self.conn.commit()
        return self.cursor.lastrowid

    def add_participant_to_event(self, event_id, user_id, is_accepted=False):
        try:
            self.cursor.execute('INSERT INTO event_participants (event_id, user_id, is_accepted) VALUES (?, ?, ?)',
                                (event_id, user_id, is_accepted))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_events_by_user(self, user_id):
        self.cursor.execute('''
            SELECT e.title, e.description, e.start_time, e.end_time, u.username, g.name
            FROM events e
            LEFT JOIN event_participants ep ON e.id = ep.event_id
            LEFT JOIN users u ON e.creator_id = u.id
            LEFT JOIN groups g ON e.group_id = g.id
            WHERE (ep.user_id = ? OR e.creator_id = ?)
              AND (ep.is_accepted = 1 OR e.creator_id = ?)
            ORDER BY e.start_time
        ''', (user_id, user_id, user_id))
        return self.cursor.fetchall()

    def check_conflict(self, user_id, start_time, end_time):
        start = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
        end = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')

        self.cursor.execute('''
            SELECT start_time, end_time FROM events e
            LEFT JOIN event_participants ep ON e.id = ep.event_id
            WHERE (ep.user_id = ? OR e.creator_id = ?)
              AND (ep.is_accepted = 1 OR e.creator_id = ?)
        ''', (user_id, user_id, user_id))

        for s, e in self.cursor.fetchall():
            if start < datetime.strptime(e, '%Y-%m-%d %H:%M:%S') and end > datetime.strptime(s, '%Y-%m-%d %H:%M:%S'):
                return True
        return False

    # ---------- Grupos ----------
    def add_group(self, name, description="", is_hierarchical=False, creator_id=None):
        try:
            self.cursor.execute('''
                INSERT INTO groups (name, description, is_hierarchical, creator_id)
                VALUES (?, ?, ?, ?)
            ''', (name, description, is_hierarchical, creator_id))
            self.conn.commit()
            group_id = self.cursor.lastrowid
            if creator_id:
                self.add_user_to_group(creator_id, group_id, True)
            return group_id
        except sqlite3.IntegrityError:
            return None

    def add_user_to_group(self, user_id, group_id, is_leader=False):
        try:
            self.cursor.execute('INSERT INTO user_groups (user_id, group_id, is_leader) VALUES (?, ?, ?)',
                                (user_id, group_id, is_leader))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def invite_user_to_group(self, group_id, invited_user_id, inviter_user_id):
        # Verificar si el usuario ya es miembro del grupo
        self.cursor.execute('''
            SELECT 1 FROM user_groups
            WHERE user_id = ? AND group_id = ?
        ''', (invited_user_id, group_id))
        if self.cursor.fetchone():
            return False  # Ya es miembro del grupo

        # Verificar si ya existe una invitación pendiente
        self.cursor.execute('''
            SELECT 1 FROM group_invitations
            WHERE group_id = ? AND invited_user_id = ? AND status = 'pending'
        ''', (group_id, invited_user_id))
        if self.cursor.fetchone():
            return False  # Ya tiene una invitación pendiente

        # Crear la invitación
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            self.cursor.execute('''
                INSERT INTO group_invitations (group_id, invited_user_id, inviter_user_id, created_at)
                VALUES (?, ?, ?, ?)
            ''', (group_id, invited_user_id, inviter_user_id, created_at))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_groups_by_user(self, user_id):
        self.cursor.execute('''
            SELECT g.id, g.name, g.is_hierarchical
            FROM groups g
            JOIN user_groups ug ON g.id = ug.group_id
            WHERE ug.user_id = ?
        ''', (user_id,))
        return self.cursor.fetchall()

    def get_group_members(self, group_id):
        self.cursor.execute('''
            SELECT u.id, u.username
            FROM users u
            JOIN user_groups ug ON u.id = ug.user_id
            WHERE ug.group_id = ?
        ''', (group_id,))
        return self.cursor.fetchall()

    def get_pending_invitations(self, user_id):
        self.cursor.execute('''
            SELECT gi.id, g.name, u.username, gi.created_at, gi.group_id
            FROM group_invitations gi
            JOIN groups g ON gi.group_id = g.id
            JOIN users u ON gi.inviter_user_id = u.id
            WHERE gi.invited_user_id = ? AND gi.status = 'pending'
            ORDER BY gi.created_at DESC
        ''', (user_id,))
        return self.cursor.fetchall()

    def respond_to_invitation(self, invitation_id, response, user_id):
        self.cursor.execute('''
            UPDATE group_invitations
            SET status = ?
            WHERE id = ? AND invited_user_id = ?
        ''', (response, invitation_id, user_id))
        if response == 'accepted':
            self.cursor.execute('SELECT group_id FROM group_invitations WHERE id = ?', (invitation_id,))
            group_id = self.cursor.fetchone()[0]
            self.cursor.execute('INSERT INTO user_groups (user_id, group_id, is_leader) VALUES (?, ?, ?)',
                                (user_id, group_id, False))
        self.conn.commit()
        return True

    def update_group(self, group_id, name=None, description=None):
        """Actualizar nombre y/o descripción de un grupo"""
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)

        if description is not None:
            updates.append("description = ?")
            params.append(description)

        if not updates:
            return True

        params.append(group_id)
        query = f"UPDATE groups SET {', '.join(updates)} WHERE id = ?"

        try:
            self.cursor.execute(query, params)
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_user_from_group(self, user_id, group_id):
        """Eliminar un usuario de un grupo"""
        try:
            self.cursor.execute('DELETE FROM user_groups WHERE user_id = ? AND group_id = ?',
                              (user_id, group_id))
            self.conn.commit()
            return True
        except Exception:
            return False

    def is_group_leader(self, user_id, group_id):
        """Verificar si un usuario es líder de un grupo"""
        self.cursor.execute('''
            SELECT is_leader FROM user_groups
            WHERE user_id = ? AND group_id = ?
        ''', (user_id, group_id))
        result = self.cursor.fetchone()
        return result and result[0]

    def get_group_info(self, group_id):
        """Obtener información completa de un grupo"""
        self.cursor.execute('''
            SELECT id, name, description, is_hierarchical, creator_id
            FROM groups WHERE id = ?
        ''', (group_id,))
        return self.cursor.fetchone()

    def delete_group(self, group_id):
        """Eliminar un grupo y todas sus relaciones (invitaciones, miembros, eventos)"""
        try:
            # Eliminar invitaciones pendientes del grupo
            self.cursor.execute('DELETE FROM group_invitations WHERE group_id = ?', (group_id,))

            # Eliminar miembros del grupo
            self.cursor.execute('DELETE FROM user_groups WHERE group_id = ?', (group_id,))

            # Eliminar participantes de eventos del grupo
            self.cursor.execute('''
                DELETE FROM event_participants
                WHERE event_id IN (SELECT id FROM events WHERE group_id = ?)
            ''', (group_id,))

            # Eliminar eventos del grupo
            self.cursor.execute('DELETE FROM events WHERE group_id = ?', (group_id,))

            # Eliminar el grupo
            self.cursor.execute('DELETE FROM groups WHERE id = ?', (group_id,))

            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error al eliminar grupo: {e}")
            self.conn.rollback()
            return False
