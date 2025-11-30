from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import httpx
import asyncio
import logging
import os

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("coordinator")

app = FastAPI(title="Coordinador RAFT - Docker Swarm", version="3.0")

# =========================================================
# 🌐 CONFIGURACIÓN PARA DOCKER SWARM
# =========================================================
SHARDS = {
    "events_a_m": [
        "http://raft_events_am_1:8801",
        "http://raft_events_am_2:8802",  
        "http://raft_events_am_3:8803",
    ],
    "events_n_z": [
        "http://raft_events_nz_1:8804",
        "http://raft_events_nz_2:8805",
        "http://raft_events_nz_3:8806",
    ],
    "groups": [
        "http://raft_groups_1:8807",
        "http://raft_groups_2:8808",
        "http://raft_groups_3:8809",
    ],
    "users": [
        "http://raft_users_1:8810",
        "http://raft_users_2:8811",
        "http://raft_users_3:8812",
    ]
}

# Cache local de líderes detectados
LEADER_CACHE = {}

# =========================================================
# 🧠 Funciones auxiliares
# =========================================================
def get_shard_for_user(username: str) -> str:
    """Determina el shard correcto según el nombre de usuario"""
    if not username:
        raise HTTPException(status_code=400, detail="Usuario inválido")
    
    first = username[0].lower()
    if 'a' <= first <= 'm':
        return "events_a_m"
    elif 'n' <= first <= 'z':
        return "events_n_z"
    else:
        return "events_a_m"  # Por defecto

async def get_leader(shard_name: str) -> str:
    """Devuelve la URL del líder actual del shard"""
    # Si tenemos líder cacheado, lo validamos rápido
    if shard_name in LEADER_CACHE:
        leader_url = LEADER_CACHE[shard_name]
        if await validate_leader(leader_url):
            return leader_url
        else:
            LEADER_CACHE.pop(shard_name, None)

    # Consultar los nodos RAFT del shard en paralelo
    tasks = [check_node_role(node_url) for node_url in SHARDS[shard_name]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, dict) and result.get("is_leader"):
            LEADER_CACHE[shard_name] = result["url"]
            logger.info(f"✅ Líder encontrado para {shard_name}: {result['url']}")
            return result["url"]

    raise HTTPException(
        status_code=503, 
        detail=f"No se encontró líder activo para el shard {shard_name}"
    )

async def check_node_role(node_url: str) -> dict:
    """Verifica el rol de un nodo específico"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{node_url}/raft/state")
            data = resp.json()
            role = data.get("role", "").lower()
            is_leader = "leader" in role
            return {"url": node_url, "is_leader": is_leader, "role": role}
    except Exception as e:
        logger.warning(f"❌ Error consultando {node_url}: {e}")
        return {"url": node_url, "is_leader": False, "error": str(e)}

async def validate_leader(url: str) -> bool:
    """Verifica si un líder cacheado sigue activo"""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{url}/raft/state")
            data = resp.json()
            role = data.get("role", "").lower()
            return "leader" in role
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
    
    try:
        leader_url = await get_leader(shard_name)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{leader_url}/events", json=event.dict())
            return resp.json()
    except HTTPException as he:
        raise he
    except Exception as e:
        # Reintento forzado con nuevo descubrimiento de líder
        logger.warning(f"⚠️ Error con líder actual, buscando nuevo líder: {e}")
        LEADER_CACHE.pop(shard_name, None)
        new_leader = await get_leader(shard_name)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{new_leader}/events", json=event.dict())
            return resp.json()

@app.post("/groups")
async def create_group(group: GroupCreate):
    try:
        leader_url = await get_leader("groups")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{leader_url}/groups", json=group.dict())
            return resp.json()
    except Exception as e:
        logger.warning(f"⚠️ Error con líder actual, buscando nuevo líder: {e}")
        LEADER_CACHE.pop("groups", None)
        new_leader = await get_leader("groups")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{new_leader}/groups", json=group.dict())
            return resp.json()

@app.post("/users")
async def create_user(user: UserCreate):
    try:
        leader_url = await get_leader("users")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{leader_url}/users", json=user.dict())
            return resp.json()
    except Exception as e:
        logger.warning(f"⚠️ Error con líder actual, buscando nuevo líder: {e}")
        LEADER_CACHE.pop("users", None)
        new_leader = await get_leader("users")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{new_leader}/users", json=user.dict())
            return resp.json()

@app.get("/events")
async def list_events(creator: str = None):
    """Lista eventos - consulta cualquier nodo del shard"""
    shard_name = get_shard_for_user(creator) if creator else "events_a_m"
    
    # Para lecturas, podemos usar cualquier nodo disponible
    for node_url in SHARDS[shard_name]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{node_url}/events")
                return resp.json()
        except Exception:
            continue
    
    raise HTTPException(status_code=503, detail="No hay nodos disponibles para consulta")

@app.get("/groups")
async def list_groups():
    """Lista grupos - consulta cualquier nodo del shard"""
    for node_url in SHARDS["groups"]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{node_url}/groups")
                return resp.json()
        except Exception:
            continue
    
    raise HTTPException(status_code=503, detail="No hay nodos disponibles para consulta")

@app.get("/users")
async def list_users():
    """Lista usuarios - consulta cualquier nodo del shard"""
    for node_url in SHARDS["users"]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{node_url}/users")
                return resp.json()
        except Exception:
            continue
    
    raise HTTPException(status_code=503, detail="No hay nodos disponibles para consulta")

@app.get("/leaders")
async def get_leaders():
    """Lista los líderes actuales por shard"""
    results = {}
    for shard in SHARDS.keys():
        try:
            leader_url = await get_leader(shard)
            results[shard] = {
                "leader": leader_url,
                "nodes": SHARDS[shard],
                "status": "active"
            }
        except Exception as e:
            results[shard] = {
                "leader": "No disponible",
                "nodes": SHARDS[shard],
                "status": "error",
                "error": str(e)
            }
    return results

@app.get("/health")
async def health_check():
    """Endpoint de salud del coordinador"""
    return {
        "status": "healthy",
        "service": "coordinator",
        "total_shards": len(SHARDS),
        "timestamp": asyncio.get_event_loop().time()
    }

@app.get("/cluster/status")
async def cluster_status():
    """Estado completo del cluster"""
    shard_status = {}
    
    for shard_name, nodes in SHARDS.items():
        node_status = {}
        for node_url in nodes:
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(f"{node_url}/health")
                    node_status[node_url] = resp.json()
            except Exception as e:
                node_status[node_url] = {"status": "unreachable", "error": str(e)}
        
        shard_status[shard_name] = node_status
    
    return {
        "coordinator": "healthy",
        "shards": shard_status,
        "total_nodes": sum(len(nodes) for nodes in SHARDS.values())
    }

@app.get("/")
def root():
    return {
        "message": "🧭 Coordinador RAFT - Docker Swarm", 
        "total_shards": len(SHARDS),
        "nodes_per_shard": 3,
        "tolerance": "Puede fallar 1 nodo por shard",
        "endpoints": {
            "create_event": "POST /events",
            "create_group": "POST /groups", 
            "create_user": "POST /users",
            "list_events": "GET /events",
            "list_groups": "GET /groups",
            "list_users": "GET /users",
            "leaders": "GET /leaders",
            "cluster_status": "GET /cluster/status"
        }
    }