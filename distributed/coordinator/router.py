from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import httpx
import asyncio

app = FastAPI(title="Coordinador Inteligente RAFT", version="2.0")

# =========================================================
# 🌐 Tabla de shards (grupos de nodos RAFT)
# =========================================================
SHARDS = {
    "events_a_m": [
        "http://localhost:8801",
        "http://localhost:8802",
        "http://localhost:8803",
    ],
    "events_n_z": [
        "http://localhost:8802",
        "http://localhost:8803",
    ],
    "groups": [
        "http://localhost:8803"
    ],
    "users": [
        "http://localhost:8804"
    ]
}

# Cache local de líderes detectados
LEADER_CACHE = {}

# =========================================================
# 🧠 Funciones auxiliares
# =========================================================
def get_shard_for_user(username: str) -> str:
    """Determina el shard correcto según el nombre de usuario"""
    first = username[0].lower()
    if 'a' <= first <= 'm':
        return "events_a_m"
    elif 'n' <= first <= 'z':
        return "events_n_z"
    raise HTTPException(status_code=400, detail="Usuario inválido")


async def get_leader(shard_name: str) -> str:
    """Devuelve la URL del líder actual del shard"""
    # Si tenemos líder cacheado, lo validamos rápido
    if shard_name in LEADER_CACHE:
        leader_url = LEADER_CACHE[shard_name]
        if await validate_leader(leader_url):
            return leader_url
        else:
            LEADER_CACHE.pop(shard_name, None)

    # Consultar los nodos RAFT del shard
    for node_url in SHARDS[shard_name]:
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                resp = await client.get(f"{node_url}/raft/state")
                data = resp.json()
                role = data.get("role") or data.get("Role")
                if role and ("leader" in str(role).lower()):
                    LEADER_CACHE[shard_name] = node_url
                    return node_url
        except Exception:
            continue

    raise HTTPException(status_code=503, detail=f"No se encontró líder activo para el shard {shard_name}")


async def validate_leader(url: str) -> bool:
    """Verifica si un líder cacheado sigue activo"""
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(f"{url}/raft/state")
            data = resp.json()
            role = data.get("role") or data.get("Role")
            return role and ("leader" in str(role).lower())
    except Exception:
        return False


# =========================================================
# 📦 Modelos Pydantic
# =========================================================
class EventCreate(BaseModel):
    title: str
    description: str
    creator: str
    start_time: str
    end_time: str


class GroupCreate(BaseModel):
    name: str
    description: str


class UserCreate(BaseModel):
    username: str
    email: str


# =========================================================
# 🎯 Endpoints principales
# =========================================================

@app.post("/events")
async def create_event(event: EventCreate):
    shard_name = get_shard_for_user(event.creator)
    leader_url = await get_leader(shard_name)

    # Intento principal
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(f"{leader_url}/events", json=event.dict())
            return resp.json()
    except Exception as e:
        print(f"⚠️ Error comunicando con líder {leader_url}: {e}")
        # Reintento forzado buscando nuevo líder
        LEADER_CACHE.pop(shard_name, None)
        new_leader = await get_leader(shard_name)
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(f"{new_leader}/events", json=event.dict())
            return resp.json()


@app.post("/groups")
async def create_group(group: GroupCreate):
    leader_url = await get_leader("groups")
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.post(f"{leader_url}/groups", json=group.dict())
        return resp.json()


@app.post("/users")
async def create_user(user: UserCreate):
    leader_url = await get_leader("users")
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.post(f"{leader_url}/users", json=user.dict())
        return resp.json()


@app.get("/leaders")
async def get_leaders():
    """Lista los líderes actuales por shard"""
    results = {}
    for shard in SHARDS.keys():
        try:
            leader_url = await get_leader(shard)
            results[shard] = leader_url
        except:
            results[shard] = "No disponible"
    return results


@app.get("/")
def root():
    return {"message": "🧭 Coordinador RAFT operativo", "total_shards": len(SHARDS)}
