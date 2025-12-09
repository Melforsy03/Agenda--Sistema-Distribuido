from fastapi import FastAPI, Request
import sqlite3
import os
import asyncio
import logging
import json
from shared.raft import RaftNode

# Configuración desde variables de entorno
SHARD_NAME = os.getenv("SHARD_NAME", "DEFAULT_SHARD")
NODE_ID = os.getenv("NODE_ID", "node0")
PORT = int(os.getenv("PORT", "8800"))
PEERS = [peer.strip() for peer in os.getenv("PEERS", "").split(",") if peer.strip()]
NODE_URL = os.getenv("NODE_URL", f"http://localhost:{PORT}")
REPLICATION_FACTOR = int(os.getenv("REPLICATION_FACTOR", "0") or 0)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(f"raft_{NODE_ID}")

app = FastAPI(title=f"Shard {SHARD_NAME} - {NODE_ID}")

# Base de datos local
os.makedirs("data", exist_ok=True)

# Configurar esquema de base de datos según el shard
if "EVENTOS" in SHARD_NAME:
    DB_PATH = os.path.join("data", f"events_{NODE_ID}.db")
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        creator TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    logger.info(f"✅ Base de datos de eventos inicializada para {NODE_ID}")

elif "GRUPOS" in SHARD_NAME:
    DB_PATH = os.path.join("data", f"groups_{NODE_ID}.db")
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        creator TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    logger.info(f"✅ Base de datos de grupos inicializada para {NODE_ID}")

elif "USUARIOS" in SHARD_NAME:
    DB_PATH = os.path.join("data", f"users_{NODE_ID}.db")
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    logger.info(f"✅ Base de datos de usuarios inicializada para {NODE_ID}")

else:
    raise ValueError(f"Shard desconocido: {SHARD_NAME}")

# Motor RAFT
logger.info(f"🔄 Inicializando nodo RAFT {NODE_ID} con peers: {PEERS}")
async def apply_log_entry(entry):
    """
    Aplica una entrada RAFT al almacén local.
    Formato esperado en entry.command: JSON con {"type": "...", "payload": {...}}
    Entradas legacy en texto plano se ignoran.
    """
    try:
        data = json.loads(entry.command)
    except Exception:
        logger.warning(f"[{NODE_ID}] Entrada legacy/inesperada, se omite: {entry.command}")
        return

    cmd_type = data.get("type")
    payload = data.get("payload", {})

    if cmd_type == "CREATE_EVENT" and "EVENTOS" in SHARD_NAME:
        cursor.execute("""
            INSERT INTO events (title, description, creator, start_time, end_time)
            VALUES (?, ?, ?, ?, ?)
        """, (
            payload.get("title"),
            payload.get("description"),
            payload.get("creator"),
            payload.get("start_time"),
            payload.get("end_time")
        ))
        conn.commit()
    elif cmd_type == "CREATE_GROUP" and "GRUPOS" in SHARD_NAME:
        cursor.execute(
            "INSERT INTO groups (name, description, creator) VALUES (?, ?, ?)",
            (
                payload.get("name"),
                payload.get("description"),
                payload.get("creator", "system")
            )
        )
        conn.commit()
    elif cmd_type == "CREATE_USER" and "USUARIOS" in SHARD_NAME:
        try:
            cursor.execute(
                "INSERT INTO users (username, email) VALUES (?, ?)", 
                (payload.get("username"), payload.get("email"))
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # Usuario/email duplicado: no es fatal
            logger.info(f"[{NODE_ID}] Usuario/email duplicado, se omite aplicar: {payload}")
    else:
        logger.warning(f"[{NODE_ID}] Tipo de comando desconocido: {cmd_type}")

raft = RaftNode(
    node_id=NODE_ID, 
    peers=PEERS, 
    state_file=f"data/{NODE_ID}_state.json",
    heartbeat_interval=1.0,
    election_timeout_range=(2.0, 4.0),
    state_machine_callback=apply_log_entry,
    self_url=NODE_URL,
    replication_factor=REPLICATION_FACTOR or None,
)

@app.on_event("startup")
async def startup():
    """Inicia el nodo RAFT al arrancar la aplicación"""
    logger.info(f"🚀 Iniciando nodo {NODE_ID} en puerto {PORT}")
    asyncio.create_task(raft.start())

# ====================================================
# Endpoints de aplicación según el shard
# ====================================================

if "EVENTOS" in SHARD_NAME:
    @app.post("/events")
    async def create_event(event: dict):
        if not raft.is_leader():
            return {"error": "No soy el líder", "leader": raft.leader_id}

        # Crear entrada de log (payload completo)
        cmd = json.dumps({"type": "CREATE_EVENT", "payload": event})
        entry = raft.append_log(cmd)

        # Replicar a seguidores
        replicated = await raft.replicate_log(entry)

        if not replicated:
            return {"error": "No se pudo replicar el evento en la mayoría de nodos"}

        # Aplicar inmediatamente en el líder y marcar progreso
        await raft.apply_to_state_machine(entry)
        raft.last_applied = max(raft.last_applied, entry.index)
        raft.save_state()

        return {
            "status": "ok", 
            "message": f"Evento '{event['title']}' replicado y guardado en {SHARD_NAME}",
            "node": NODE_ID
        }

    @app.get("/events")
    def list_events():
        cursor.execute("SELECT id, title, creator, start_time, end_time FROM events")
        rows = cursor.fetchall()
        return [{
            "id": r[0], 
            "title": r[1], 
            "creator": r[2], 
            "start_time": r[3],
            "end_time": r[4]
        } for r in rows]

elif "GRUPOS" in SHARD_NAME:
    @app.post("/groups")
    async def create_group(group: dict):
        if not raft.is_leader():
            return {"error": "No soy el líder", "leader": raft.leader_id}

        cmd = json.dumps({"type": "CREATE_GROUP", "payload": group})
        entry = raft.append_log(cmd)
        replicated = await raft.replicate_log(entry)

        if not replicated:
            return {"error": "No se pudo replicar el grupo en la mayoría de nodos"}

        await raft.apply_to_state_machine(entry)
        raft.last_applied = max(raft.last_applied, entry.index)
        raft.save_state()

        return {
            "status": "ok", 
            "message": f"Grupo '{group['name']}' creado en {SHARD_NAME}",
            "node": NODE_ID
        }

    @app.get("/groups")
    def list_groups():
        cursor.execute("SELECT id, name, description, creator FROM groups")
        return [{
            "id": r[0], 
            "name": r[1], 
            "description": r[2],
            "creator": r[3]
        } for r in cursor.fetchall()]

elif "USUARIOS" in SHARD_NAME:
    @app.post("/users")
    async def create_user(user: dict):
        if not raft.is_leader():
            return {"error": "No soy el líder", "leader": raft.leader_id}

        cmd = json.dumps({"type": "CREATE_USER", "payload": user})
        entry = raft.append_log(cmd)
        replicated = await raft.replicate_log(entry)

        if not replicated:
            return {"error": "No se pudo replicar el usuario en la mayoría de nodos"}

        await raft.apply_to_state_machine(entry)
        raft.last_applied = max(raft.last_applied, entry.index)
        raft.save_state()

        return {
            "status": "ok", 
            "message": f"Usuario '{user['username']}' creado en {SHARD_NAME}",
            "node": NODE_ID
        }

    @app.get("/users")
    def list_users():
        cursor.execute("SELECT id, username, email FROM users")
        return [{
            "id": r[0], 
            "username": r[1], 
            "email": r[2]
        } for r in cursor.fetchall()]

# ====================================================
# Endpoints RAFT (comunes para todos los nodos)
# ====================================================

@app.get("/raft/state")
def state():
    return {
        "role": raft.role.value if hasattr(raft.role, 'value') else str(raft.role),
        "term": raft.current_term, 
        "leader": raft.leader_id,
        "node_id": NODE_ID,
        "shard": SHARD_NAME
    }

@app.post("/raft/request_vote")
async def request_vote(req: Request):
    data = await req.json()
    return await raft.handle_vote_request(
        data["term"], 
        data["candidate_id"],
        data.get("last_log_index", 0),
        data.get("last_log_term", 0)
    )

@app.post("/raft/append_entries")
async def append_entries(req: Request):
    data = await req.json()
    return await raft.receive_append_entries(
        data["term"], 
        data["leader_id"], 
        data.get("entries", []),
        data.get("prev_log_index", 0),
        data.get("prev_log_term", 0),
        data.get("leader_commit", 0)
    )

@app.post("/raft/heartbeat")
async def heartbeat(req: Request):
    data = await req.json()
    await raft.receive_heartbeat(data["term"], data["leader_id"])
    return {"status": "ok"}

# Bully election endpoints
@app.post("/raft/bully/challenge")
async def bully_challenge(req: Request):
    data = await req.json()
    return await raft.handle_bully_challenge(
        data.get("candidate_id", ""),
        data.get("candidate_url", ""),
        data.get("priority", 0)
    )

@app.post("/raft/bully/victory")
async def bully_victory(req: Request):
    data = await req.json()
    return await raft.handle_bully_victory(
        data.get("leader_id", ""),
        data.get("leader_url", ""),
        data.get("priority", 0)
    )

@app.get("/raft/sync")
def sync_log(follower: str):
    """Devuelve entradas del log al seguidor que se reconecta"""
    return {"missing_entries": [e.to_dict() for e in raft.log]}

@app.get("/raft/log/summary")
def log_summary():
    last_index = len(raft.log)
    last_term = raft.log[-1].term if raft.log else 0
    return {
        "last_index": last_index,
        "last_term": last_term,
        "commit_index": raft.commit_index,
        "node_id": NODE_ID,
        "role": raft.role.value if hasattr(raft.role, 'value') else str(raft.role)
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "node_id": NODE_ID,
        "role": raft.role.value if hasattr(raft.role, 'value') else str(raft.role),
        "shard": SHARD_NAME,
        "is_leader": raft.is_leader(),
        "term": raft.current_term
    }

@app.get("/")
def root():
    return {
        "message": f"Nodo RAFT {NODE_ID} - Shard {SHARD_NAME}",
        "role": raft.role.value if hasattr(raft.role, 'value') else str(raft.role),
        "is_leader": raft.is_leader(),
        "peers": PEERS
    }
