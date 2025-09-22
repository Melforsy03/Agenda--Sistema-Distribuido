import sqlite3
import bcrypt
from datetime import datetime

def setup_database(db_name='agenda.db'):
    """
    Crea la base de datos y las tablas necesarias para el proyecto.
    """
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Tabla para usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        );
    ''')

    # Tabla para grupos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            is_hierarchical BOOLEAN NOT NULL,
            creator_id INTEGER,
            FOREIGN KEY (creator_id) REFERENCES users(id)
        );
    ''')
    
    # Migración: agregar columnas si no existen
    try:
        cursor.execute('ALTER TABLE groups ADD COLUMN creator_id INTEGER')
    except:
        pass  # La columna ya existe
    
    try:
        cursor.execute('ALTER TABLE groups ADD COLUMN description TEXT')
    except:
        pass  # La columna ya existe

    # Tabla para eventos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            creator_id INTEGER NOT NULL,
            group_id INTEGER,
            is_group_event BOOLEAN NOT NULL DEFAULT 0,
            FOREIGN KEY (creator_id) REFERENCES users(id),
            FOREIGN KEY (group_id) REFERENCES groups(id)
        );
    ''')

    # Tabla de unión para miembros del grupo
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_groups (
            user_id INTEGER,
            group_id INTEGER,
            is_leader BOOLEAN NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, group_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (group_id) REFERENCES groups(id)
        );
    ''')

    # Tabla de unión para participantes del evento y su estado de invitación
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS event_participants (
            event_id INTEGER,
            user_id INTEGER,
            is_accepted BOOLEAN NOT NULL DEFAULT 0,
            PRIMARY KEY (event_id, user_id),
            FOREIGN KEY (event_id) REFERENCES events(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')

    # Tabla para invitaciones a grupos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS group_invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            invited_user_id INTEGER NOT NULL,
            inviter_user_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (group_id) REFERENCES groups(id),
            FOREIGN KEY (invited_user_id) REFERENCES users(id),
            FOREIGN KEY (inviter_user_id) REFERENCES users(id)
        );
    ''')

    conn.commit()
    conn.close()

class Database:
    def __init__(self, db_name='agenda.db'):
        self.db_name = db_name
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()

    def close(self):
        """Cierra la conexión a la base de datos."""
        self.conn.close()

    def get_user(self, username):
        """Busca un usuario por nombre de usuario."""
        self.cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        return self.cursor.fetchone()

    def add_user(self, username, password):
        """Registra un nuevo usuario con una contraseña hasheada."""
        try:
            password_bytes = password.encode('utf-8')
            password_hash = bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode('utf-8')
            self.cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, password_hash))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def check_password(self, username, password):
        """Verifica la contraseña de un usuario."""
        user = self.get_user(username)
        if user:
            password_hash = user[2].encode('utf-8')
            return bcrypt.checkpw(password.encode('utf-8'), password_hash)
        return False

    def get_user_id(self, username):
        """Obtiene el ID de un usuario por su nombre de usuario."""
        self.cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        result = self.cursor.fetchone()
        return result[0] if result else None
    
    def get_username(self, user_id):
        """Obtiene el nombre de usuario por su ID."""
        self.cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def get_all_users(self):
        """Obtiene una lista de todos los usuarios (para invitar a eventos)."""
        self.cursor.execute('SELECT id, username FROM users')
        return self.cursor.fetchall()

    def add_event(self, title, description, start_time, end_time, creator_id, group_id=None, is_group_event=False):
        """Crea un nuevo evento."""
        self.cursor.execute(
            'INSERT INTO events (title, description, start_time, end_time, creator_id, group_id, is_group_event) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (title, description, start_time, end_time, creator_id, group_id, is_group_event)
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def add_participant_to_event(self, event_id, user_id, is_accepted=False):
        """Añade un participante a un evento."""
        try:
            self.cursor.execute('INSERT INTO event_participants (event_id, user_id, is_accepted) VALUES (?, ?, ?)', (event_id, user_id, is_accepted))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_events_by_user(self, user_id):
        """Obtiene todos los eventos de un usuario (personales y grupales)."""
        self.cursor.execute('''
            SELECT e.title, e.description, e.start_time, e.end_time, u.username, g.name
            FROM events e
            LEFT JOIN event_participants ep ON e.id = ep.event_id
            LEFT JOIN users u ON e.creator_id = u.id
            LEFT JOIN groups g ON e.group_id = g.id
            WHERE (ep.user_id = ? OR e.creator_id = ?)
            ORDER BY e.start_time
        ''', (user_id, user_id))
        return self.cursor.fetchall()

    def get_group_members(self, group_id):
        """Obtiene los miembros de un grupo por su ID."""
        self.cursor.execute('''
            SELECT u.id, u.username
            FROM users u
            JOIN user_groups ug ON u.id = ug.user_id
            WHERE ug.group_id = ?
        ''', (group_id,))
        return self.cursor.fetchall()

    def add_group(self, name, description="", is_hierarchical=False, creator_id=None):
        """Crea un nuevo grupo."""
        try:
            self.cursor.execute('INSERT INTO groups (name, description, is_hierarchical, creator_id) VALUES (?, ?, ?, ?)', 
                              (name, description, is_hierarchical, creator_id))
            self.conn.commit()
            group_id = self.cursor.lastrowid
            
            # Agregar al creador como líder del grupo
            if creator_id:
                self.add_user_to_group(creator_id, group_id, is_leader=True)
            
            return group_id
        except sqlite3.IntegrityError:
            return None

    def add_user_to_group(self, user_id, group_id, is_leader=False):
        """Añade un usuario a un grupo directamente (solo para líderes/creadores)."""
        try:
            self.cursor.execute('INSERT INTO user_groups (user_id, group_id, is_leader) VALUES (?, ?, ?)', (user_id, group_id, is_leader))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def invite_user_to_group(self, group_id, invited_user_id, inviter_user_id):
        """Envía una invitación a un usuario para unirse a un grupo."""
        try:
            created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.cursor.execute('''
                INSERT INTO group_invitations (group_id, invited_user_id, inviter_user_id, created_at) 
                VALUES (?, ?, ?, ?)
            ''', (group_id, invited_user_id, inviter_user_id, created_at))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_pending_invitations(self, user_id):
        """Obtiene las invitaciones pendientes de un usuario."""
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
        """Responde a una invitación de grupo (accept/decline)."""
        try:
            # Actualizar el estado de la invitación
            self.cursor.execute('''
                UPDATE group_invitations 
                SET status = ? 
                WHERE id = ? AND invited_user_id = ?
            ''', (response, invitation_id, user_id))
            
            # Si se acepta, agregar al grupo
            if response == 'accepted':
                # Obtener los datos de la invitación
                self.cursor.execute('''
                    SELECT group_id FROM group_invitations WHERE id = ?
                ''', (invitation_id,))
                result = self.cursor.fetchone()
                if result:
                    group_id = result[0]
                    self.cursor.execute('''
                        INSERT INTO user_groups (user_id, group_id, is_leader) VALUES (?, ?, ?)
                    ''', (user_id, group_id, False))
            
            self.conn.commit()
            return True
        except sqlite3.Error:
            return False

    def get_groups_by_user(self, user_id):
        """Obtiene los grupos a los que pertenece un usuario."""
        self.cursor.execute('SELECT g.id, g.name, g.is_hierarchical FROM groups g JOIN user_groups ug ON g.id = ug.group_id WHERE ug.user_id = ?', (user_id,))
        return self.cursor.fetchall()

    def check_conflict(self, user_id, start_time, end_time):
        """
        Verifica si hay un conflicto de horarios para un usuario.
        """
        start = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
        end = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
        
        self.cursor.execute('''
            SELECT start_time, end_time FROM events e
            LEFT JOIN event_participants ep ON e.id = ep.event_id
            WHERE (ep.user_id = ? OR e.creator_id = ?)
        ''', (user_id, user_id))
        
        events = self.cursor.fetchall()
        
        for event in events:
            existing_start = datetime.strptime(event[0], '%Y-%m-%d %H:%M:%S')
            existing_end = datetime.strptime(event[1], '%Y-%m-%d %H:%M:%S')
            
            # Condición de superposición
            if (start < existing_end and end > existing_start):
                return True # Conflicto detectado
        return False # No hay conflictos
    
    def get_events_by_user_on_date(self, user_id, date_str):
        """Obtiene los eventos de un usuario para un día específico."""
        self.cursor.execute('''
            SELECT e.title, e.description, e.start_time, e.end_time, u.username, g.name
            FROM events e
            LEFT JOIN event_participants ep ON e.id = ep.event_id
            LEFT JOIN users u ON e.creator_id = u.id
            LEFT JOIN groups g ON e.group_id = g.id
            WHERE (ep.user_id = ? OR e.creator_id = ?) AND SUBSTR(e.start_time, 1, 10) = ?
            ORDER BY e.start_time
        ''', (user_id, user_id, date_str))
        return self.cursor.fetchall()
    
    # Continúa en la clase Database...

    def get_events_in_date_range(self, user_id, start_date_str, end_date_str):
        """Obtiene los eventos de un usuario dentro de un rango de fechas."""
        self.cursor.execute('''
            SELECT e.title, e.description, e.start_time, e.end_time, u.username, g.name
            FROM events e
            LEFT JOIN event_participants ep ON e.id = ep.event_id
            LEFT JOIN users u ON e.creator_id = u.id
            LEFT JOIN groups g ON e.group_id = g.id
            WHERE (ep.user_id = ? OR e.creator_id = ?) AND e.start_time BETWEEN ? AND ?
            ORDER BY e.start_time
        ''', (user_id, user_id, start_date_str, end_date_str))
        return self.cursor.fetchall()

    def is_group_creator(self, user_id, group_id):
        """Verifica si el usuario es el creador del grupo."""
        self.cursor.execute('SELECT creator_id FROM groups WHERE id = ?', (group_id,))
        result = self.cursor.fetchone()
        return result and result[0] == user_id

    def update_group_info(self, group_id, name, description):
        """Actualiza el nombre y descripción de un grupo."""
        try:
            self.cursor.execute('''
                UPDATE groups SET name = ?, description = ? WHERE id = ?
            ''', (name, description, group_id))
            self.conn.commit()
            return True
        except:
            return False

    def remove_user_from_group(self, user_id, group_id):
        """Remueve un usuario de un grupo."""
        try:
            self.cursor.execute('DELETE FROM user_groups WHERE user_id = ? AND group_id = ?', (user_id, group_id))
            self.conn.commit()
            return True
        except:
            return False

    def get_group_details(self, group_id):
        """Obtiene los detalles completos de un grupo."""
        self.cursor.execute('''
            SELECT g.id, g.name, g.description, g.is_hierarchical, g.creator_id, u.username as creator_name
            FROM groups g
            JOIN users u ON g.creator_id = u.id
            WHERE g.id = ?
        ''', (group_id,))
        return self.cursor.fetchone()

    def delete_group(self, group_id):
        """Elimina un grupo y todas sus relaciones."""
        try:
            # Eliminar primero las relaciones para evitar violaciones de clave foránea
            self.cursor.execute('DELETE FROM user_groups WHERE group_id = ?', (group_id,))
            self.cursor.execute('DELETE FROM group_invitations WHERE group_id = ?', (group_id,))
            # También eliminar eventos asociados al grupo si los hay
            self.cursor.execute('DELETE FROM events WHERE group_id = ?', (group_id,))
            # Finalmente eliminar el grupo
            self.cursor.execute('DELETE FROM groups WHERE id = ?', (group_id,))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error al eliminar grupo: {e}")
            return False

if __name__ == '__main__':
    setup_database()
    print("Base de datos 'agenda.db' y tablas inicializadas correctamente.")