import asyncio
import aiohttp
import json
import os
import random
import time
from enum import Enum
from typing import List, Optional, Dict, Any
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("raft")

class RaftRole(str, Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"

class LogEntry:
    """Una entrada en el log de RAFT"""
    def __init__(self, term: int, command: str, index: int = None):
        self.term = term
        self.command = command
        self.index = index

    def to_dict(self):
        return {"term": self.term, "command": self.command, "index": self.index}

    @staticmethod
    def from_dict(d):
        return LogEntry(term=d["term"], command=d["command"], index=d.get("index"))

class RaftNode:
    """
    Nodo RAFT con consenso completo y tolerancia a fallos
    """

    def __init__(self, node_id: str, peers: List[str], state_file: str, 
                 heartbeat_interval: float = 1.0, election_timeout_range: tuple = (2.0, 4.0)):
        self.node_id = node_id
        self.peers = peers
        self.state_file = state_file
        
        # Estado RAFT persistente
        self.current_term = 0
        self.voted_for: Optional[str] = None
        self.log: List[LogEntry] = []
        
        # Estado RAFT volátil
        self.commit_index = 0
        self.last_applied = 0
        self.role = RaftRole.FOLLOWER
        self.leader_id: Optional[str] = None
        self.votes_received = set()
        
        # Para líderes
        self.next_index: Dict[str, int] = {}
        self.match_index: Dict[str, int] = {}
        
        # Configuración de timeouts
        self.heartbeat_interval = heartbeat_interval
        self.election_timeout_range = election_timeout_range
        self.election_timeout = self._random_election_timeout()
        self.last_heartbeat_time = time.time()
        
        # Bloqueo para operaciones concurrentes
        self._lock = asyncio.Lock()
        
        # Cargar estado persistente
        self.load_state()
        
        # Inicializar índices de replicación si es líder
        if self.role == RaftRole.LEADER:
            self._init_leader_state()

    def _random_election_timeout(self) -> float:
        min_timeout, max_timeout = self.election_timeout_range
        return random.uniform(min_timeout, max_timeout)

    def _init_leader_state(self):
        """Inicializa el estado específico del líder"""
        for peer in self.peers:
            self.next_index[peer] = len(self.log) + 1
            self.match_index[peer] = 0

    # ====================================================
    # Persistencia
    # ====================================================

    def save_state(self):
        """Guarda el estado persistente en disco"""
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        state = {
            "current_term": self.current_term,
            "voted_for": self.voted_for,
            "log": [e.to_dict() for e in self.log],
            "commit_index": self.commit_index,
        }
        try:
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Error guardando estado: {e}")

    def load_state(self):
        """Carga el estado persistente desde disco"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    state = json.load(f)
                self.current_term = state.get("current_term", 0)
                self.voted_for = state.get("voted_for")
                
                # Reconstruir log con índices
                log_data = state.get("log", [])
                self.log = []
                for i, entry_data in enumerate(log_data):
                    entry = LogEntry.from_dict(entry_data)
                    entry.index = i + 1
                    self.log.append(entry)
                
                self.commit_index = state.get("commit_index", 0)
                logger.info(f"✅ Estado cargado: término {self.current_term}, {len(self.log)} entradas")
            except Exception as e:
                logger.error(f"Error cargando estado: {e}")

    # ====================================================
    # Estado interno
    # ====================================================

    def is_leader(self) -> bool:
        return self.role == RaftRole.LEADER

    def reset_election_timer(self):
        """Reinicia el temporizador de elección"""
        self.last_heartbeat_time = time.time()
        self.election_timeout = self._random_election_timeout()

    # ====================================================
    # Ciclo principal
    # ====================================================

    async def start(self):
        """Inicia las tareas del nodo RAFT"""
        logger.info(f"🚀 Iniciando nodo {self.node_id} como {self.role}")
        asyncio.create_task(self._election_loop())
        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._apply_committed_entries())

    async def _election_loop(self):
        """Maneja las elecciones de líder"""
        while True:
            await asyncio.sleep(0.1)
            
            if self.role == RaftRole.LEADER:
                continue

            # Verificar timeout de elección
            if time.time() - self.last_heartbeat_time > self.election_timeout:
                await self._start_election()

    async def _heartbeat_loop(self):
        """Loop para enviar heartbeats (solo líderes)"""
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            if self.role == RaftRole.LEADER:
                await self._broadcast_heartbeat()

    async def _apply_committed_entries(self):
        """Aplica las entradas comprometidas a la máquina de estado"""
        while True:
            await asyncio.sleep(0.5)
            while self.last_applied < self.commit_index:
                if self.last_applied < len(self.log):
                    entry = self.log[self.last_applied]
                    await self.apply_to_state_machine(entry)
                self.last_applied += 1

    # ====================================================
    # Elecciones de líder
    # ====================================================

    async def _start_election(self):
        """Inicia una nueva elección"""
        async with self._lock:
            self.role = RaftRole.CANDIDATE
            self.current_term += 1
            self.voted_for = self.node_id
            self.votes_received = {self.node_id}
            self.reset_election_timer()
            self.save_state()

        logger.info(f"🗳️ {self.node_id} inicia elección (término {self.current_term})")

        # Solicitar votos a todos los peers
        tasks = []
        for peer in self.peers:
            task = asyncio.create_task(self._request_vote(peer))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Contar votos
        successful_votes = sum(1 for r in results if r is True)
        total_nodes = len(self.peers) + 1  # +1 por sí mismo
        majority_required = (total_nodes // 2) + 1
        
        if len(self.votes_received) >= majority_required:
            async with self._lock:
                self.role = RaftRole.LEADER
                self.leader_id = self.node_id
                self._init_leader_state()
            logger.info(f"👑 {self.node_id} elegido LÍDER (término {self.current_term})")
            # Enviar heartbeats inmediatamente
            await self._broadcast_heartbeat()
        else:
            logger.info(f"❌ {self.node_id} no obtuvo mayoría ({len(self.votes_received)}/{majority_required})")

    async def _request_vote(self, peer: str) -> bool:
        """Solicita voto a un peer específico"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                data = {
                    "term": self.current_term,
                    "candidate_id": self.node_id,
                    "last_log_index": len(self.log),
                    "last_log_term": self.log[-1].term if self.log else 0
                }
                async with session.post(f"{peer}/raft/request_vote", json=data) as resp:
                    result = await resp.json()
                    if result.get("vote_granted", False):
                        self.votes_received.add(peer)
                        return True
        except Exception as e:
            logger.warning(f"Error solicitando voto a {peer}: {e}")
        return False

    # ====================================================
    # Heartbeats y replicación
    # ====================================================

    async def _broadcast_heartbeat(self):
        """Envía heartbeats a todos los seguidores"""
        if not self.is_leader():
            return

        tasks = []
        for peer in self.peers:
            task = asyncio.create_task(self._send_append_entries(peer))
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_append_entries(self, peer: str):
        """Envía AppendEntries RPC a un seguidor"""
        try:
            next_idx = self.next_index.get(peer, 1)
            prev_log_index = next_idx - 1
            prev_log_term = 0
            
            if prev_log_index > 0 and prev_log_index <= len(self.log):
                prev_log_term = self.log[prev_log_index - 1].term
            
            entries = []
            if next_idx <= len(self.log):
                entries = [entry.to_dict() for entry in self.log[next_idx - 1:]]

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
                data = {
                    "term": self.current_term,
                    "leader_id": self.node_id,
                    "prev_log_index": prev_log_index,
                    "prev_log_term": prev_log_term,
                    "entries": entries,
                    "leader_commit": self.commit_index
                }
                async with session.post(f"{peer}/raft/append_entries", json=data) as resp:
                    result = await resp.json()
                    
                    if result.get("success", False):
                        # Actualizar índices de replicación
                        self.next_index[peer] = len(self.log) + 1
                        self.match_index[peer] = len(self.log)
                        
                        # Verificar si podemos comprometer nuevas entradas
                        await self._update_commit_index()
                    else:
                        # Retroceder next_index
                        if self.next_index[peer] > 1:
                            self.next_index[peer] -= 1
        except Exception as e:
            logger.warning(f"Error enviando AppendEntries a {peer}: {e}")

    async def _update_commit_index(self):
        """Actualiza el commit_index basado en las réplicas"""
        if not self.is_leader():
            return

        # Encontrar el índice más alto que está replicado en la mayoría
        for n in range(len(self.log), self.commit_index, -1):
            count = 1  # El líder cuenta
            for peer in self.peers:
                if self.match_index.get(peer, 0) >= n:
                    count += 1
            
            if count > (len(self.peers) + 1) // 2:
                if n > self.commit_index and self.log[n-1].term == self.current_term:
                    self.commit_index = n
                    self.save_state()
                break

    # ====================================================
    # API para aplicaciones
    # ====================================================

    def append_log(self, command: str) -> LogEntry:
        """Agrega una nueva entrada al log (solo líder)"""
        if not self.is_leader():
            raise Exception("Solo el líder puede agregar entradas al log")
        
        entry = LogEntry(self.current_term, command, index=len(self.log) + 1)
        self.log.append(entry)
        self.save_state()
        return entry

    async def replicate_log(self, entry: LogEntry) -> bool:
        """Replica una entrada a la mayoría de nodos"""
        if not self.is_leader():
            return False

        # La entrada ya está en el log del líder, ahora replicarla
        success_count = 1  # El líder cuenta
        
        tasks = []
        for peer in self.peers:
            task = asyncio.create_task(self._replicate_entry_to_peer(peer, entry))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        success_count += sum(1 for r in results if r is True)

        # Verificar mayoría
        total_nodes = len(self.peers) + 1
        majority_required = (total_nodes // 2) + 1
        
        has_majority = success_count >= majority_required
        
        if has_majority:
            # Actualizar commit_index si es mayor que el actual
            entry_index = entry.index
            if entry_index > self.commit_index:
                self.commit_index = entry_index
                self.save_state()
            logger.info(f"✅ Entrada {entry_index} replicada en mayoría")
        else:
            logger.warning(f"⚠️ Entrada {entry.index} no alcanzó mayoría ({success_count}/{majority_required})")

        return has_majority

    async def _replicate_entry_to_peer(self, peer: str, entry: LogEntry) -> bool:
        """Replica una entrada específica a un peer"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                data = {
                    "term": self.current_term,
                    "leader_id": self.node_id,
                    "entries": [entry.to_dict()],
                    "leader_commit": self.commit_index
                }
                async with session.post(f"{peer}/raft/append_entries", json=data) as resp:
                    result = await resp.json()
                    return result.get("success", False)
        except Exception as e:
            logger.warning(f"Error replicando a {peer}: {e}")
            return False

    # ====================================================
    # Handlers para requests RAFT
    # ====================================================

    async def handle_vote_request(self, term: int, candidate_id: str, 
                                last_log_index: int, last_log_term: int) -> dict:
        """Maneja RequestVote RPC"""
        async with self._lock:
            # Actualizar término si es necesario
            if term > self.current_term:
                self.current_term = term
                self.role = RaftRole.FOLLOWER
                self.voted_for = None
                self.save_state()

            vote_granted = False
            
            # Verificar condiciones para otorgar voto
            if (term == self.current_term and 
                (self.voted_for is None or self.voted_for == candidate_id)):
                
                # Verificar que el log del candidato está al menos tan actualizado como el nuestro
                our_last_log_term = self.log[-1].term if self.log else 0
                our_last_log_index = len(self.log)
                
                if (last_log_term > our_last_log_term or 
                    (last_log_term == our_last_log_term and last_log_index >= our_last_log_index)):
                    
                    self.voted_for = candidate_id
                    vote_granted = True
                    self.reset_election_timer()
                    self.save_state()

            return {
                "term": self.current_term,
                "vote_granted": vote_granted,
                "node_id": self.node_id
            }

    async def receive_append_entries(self, term: int, leader_id: str, 
                                   entries: List[dict], prev_log_index: int, 
                                   prev_log_term: int, leader_commit: int) -> dict:
        """Maneja AppendEntries RPC"""
        async with self._lock:
            # Actualizar término si es necesario
            if term > self.current_term:
                self.current_term = term
                self.role = RaftRole.FOLLOWER
                self.voted_for = None

            success = False

            if term < self.current_term:
                return {"term": self.current_term, "success": False}

            # Resetear temporizador de elección
            self.reset_election_timer()
            self.role = RaftRole.FOLLOWER
            self.leader_id = leader_id

            # Verificar consistencia del log
            if prev_log_index > 0:
                if prev_log_index > len(self.log) or \
                   (prev_log_index <= len(self.log) and self.log[prev_log_index - 1].term != prev_log_term):
                    return {"term": self.current_term, "success": False}

            # Aplicar entradas
            if entries:
                # Eliminar entradas conflictivas
                if prev_log_index < len(self.log):
                    self.log = self.log[:prev_log_index]
                
                # Agregar nuevas entradas
                for entry_data in entries:
                    entry = LogEntry.from_dict(entry_data)
                    entry.index = len(self.log) + 1
                    self.log.append(entry)

            # Actualizar commit_index
            if leader_commit > self.commit_index:
                self.commit_index = min(leader_commit, len(self.log))

            success = True
            self.save_state()

            return {
                "term": self.current_term,
                "success": success,
                "node_id": self.node_id
            }

    async def receive_heartbeat(self, term: int, leader_id: str):
        """Maneja heartbeat simple"""
        async with self._lock:
            if term >= self.current_term:
                self.current_term = term
                self.role = RaftRole.FOLLOWER
                self.leader_id = leader_id
                self.reset_election_timer()
                self.save_state()

    # ====================================================
    # Sincronización
    # ====================================================

    async def request_log_sync(self):
        """Solicita sincronización de log al líder"""
        if not self.leader_id or self.is_leader():
            return

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{self.leader_id}/raft/sync?follower={self.node_id}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        missing_entries = data.get("missing_entries", [])
                        for entry_data in missing_entries:
                            entry = LogEntry.from_dict(entry_data)
                            if entry.index > len(self.log):
                                self.log.append(entry)
                        self.save_state()
                        logger.info(f"✅ Sincronizadas {len(missing_entries)} entradas desde líder")
        except Exception as e:
            logger.warning(f"Error sincronizando con líder: {e}")

    # ====================================================
    # Aplicación a máquina de estado
    # ====================================================

    async def apply_to_state_machine(self, entry: LogEntry):
        """Aplica una entrada comprometida a la máquina de estado"""
        # Esta función debe ser implementada por la aplicación específica
        logger.info(f"📥 [{self.node_id}] Aplicando: {entry.command} (índice {entry.index})")
        # La aplicación real actualizará su base de datos aquí