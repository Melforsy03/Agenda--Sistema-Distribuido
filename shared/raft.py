import asyncio
import aiohttp
import json
import os
import random
import time
from enum import Enum
from typing import List, Optional


class RaftRole(str, Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


class LogEntry:
    """Una entrada en el log de RAFT"""
    def __init__(self, term: int, command: str):
        self.term = term
        self.command = command

    def to_dict(self):
        return {"term": self.term, "command": self.command}

    @staticmethod
    def from_dict(d):
        return LogEntry(term=d["term"], command=d["command"])


class RaftNode:
    """
    Nodo RAFT con consenso completo:
    - Elección de líder
    - Replicación de logs
    - Heartbeats
    - Aplicación de commits
    - Sincronización automática al reconectar
    """

    def __init__(self, node_id: str, peers: List[str], state_file="data/raft_state.json"):
        self.node_id = node_id
        self.peers = peers
        self.state_file = state_file

        # Estado persistente
        self.current_term = 0
        self.voted_for: Optional[str] = None
        self.log: List[LogEntry] = []

        # Estado volátil
        self.commit_index = 0
        self.last_applied = 0
        self.role = RaftRole.FOLLOWER
        self.leader_id: Optional[str] = None

        # Temporizadores
        self.election_timeout = random.uniform(3, 5)
        self.last_heartbeat = time.time()

        # Bloqueo asíncrono
        self._lock = asyncio.Lock()

        # Cargar estado persistente
        self.load_state()

    # ====================================================
    # Persistencia
    # ====================================================

    def save_state(self):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        state = {
            "current_term": self.current_term,
            "voted_for": self.voted_for,
            "log": [e.to_dict() for e in self.log],
            "commit_index": self.commit_index,
            "last_applied": self.last_applied,
        }
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)

    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    state = json.load(f)
                self.current_term = state.get("current_term", 0)
                self.voted_for = state.get("voted_for")
                self.log = [LogEntry.from_dict(e) for e in state.get("log", [])]
                self.commit_index = state.get("commit_index", 0)
                self.last_applied = state.get("last_applied", 0)
            except Exception:
                pass

    # ====================================================
    # Estado interno
    # ====================================================

    def is_leader(self) -> bool:
        return self.role == RaftRole.LEADER

    def reset_election_timer(self):
        self.last_heartbeat = time.time()
        self.election_timeout = random.uniform(3, 5)

    # ====================================================
    # Ciclo principal
    # ====================================================

    async def start(self):
        """Inicia las tareas del nodo RAFT"""
        asyncio.create_task(self._election_loop())
        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self.apply_committed_entries())

    # ====================================================
    # Elecciones de líder
    # ====================================================

    async def _election_loop(self):
        """Maneja las elecciones de líder"""
        while True:
            await asyncio.sleep(0.5)
            if self.is_leader():
                continue

            # Si no hay heartbeats, iniciar elección
            if time.time() - self.last_heartbeat > self.election_timeout:
                await self.start_election()

    async def start_election(self):
        async with self._lock:
            self.role = RaftRole.CANDIDATE
            self.current_term += 1
            self.voted_for = self.node_id
            self.reset_election_timer()
            votes_received = 1  # Se vota a sí mismo

        print(f"🗳️ Nodo {self.node_id} inicia elección (term {self.current_term})")

        async with aiohttp.ClientSession() as session:
            tasks = [self._send_request_vote(session, peer) for peer in self.peers]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        votes = sum(1 for r in results if r is True)
        majority = (len(self.peers) + 1) // 2 + 1

        if votes + 1 >= majority:
            async with self._lock:
                self.role = RaftRole.LEADER
                self.leader_id = self.node_id
            print(f"👑 Nodo {self.node_id} es ahora LÍDER (term {self.current_term})")
        else:
            async with self._lock:
                self.role = RaftRole.FOLLOWER

    async def _send_request_vote(self, session, peer):
        try:
            async with session.post(f"{peer}/raft/request_vote", json={
                "term": self.current_term,
                "candidate_id": self.node_id
            }, timeout=2) as resp:
                data = await resp.json()
                return data.get("vote_granted", False)
        except Exception:
            return False

    # ====================================================
    # Heartbeats y detección de fallos
    # ====================================================

    async def _heartbeat_loop(self):
        while True:
            await asyncio.sleep(1)
            if self.is_leader():
                await self.broadcast_heartbeat()

    async def broadcast_heartbeat(self):
        async with aiohttp.ClientSession() as session:
            tasks = [self._send_heartbeat(session, peer) for peer in self.peers]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_heartbeat(self, session, peer):
        try:
            async with session.post(f"{peer}/raft/heartbeat", json={
                "term": self.current_term,
                "leader_id": self.node_id
            }, timeout=2):
                pass
        except Exception:
            pass

    async def receive_heartbeat(self, term: int, leader_id: str):
        async with self._lock:
            if term >= self.current_term:
                self.role = RaftRole.FOLLOWER
                self.leader_id = leader_id
                self.current_term = term
                self.reset_election_timer()
                self.save_state()
                # 🔄 Pedir sincronización si se detecta desfase
                await self.request_log_sync()

    # ====================================================
    # Replicación de logs
    # ====================================================

    def append_log(self, command: str):
        """Agregar una entrada al log (solo el líder)"""
        if not self.is_leader():
            raise Exception("Solo el líder puede agregar comandos")
        entry = LogEntry(self.current_term, command)
        self.log.append(entry)
        self.save_state()
        return entry

    async def replicate_log(self, entry: LogEntry):
        """El líder envía la entrada a los seguidores y espera confirmaciones"""
        if not self.is_leader():
            return False

        success_count = 1  # el líder cuenta como voto propio
        async with aiohttp.ClientSession() as session:
            tasks = [self._send_append_entries(session, peer, entry) for peer in self.peers]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if r is True:
                success_count += 1

        majority = (len(self.peers) + 1) // 2 + 1
        if success_count >= majority:
            print(f"✅ Entrada replicada en mayoría (term {self.current_term})")
            self.commit_index = len(self.log)
            self.save_state()
            return True
        else:
            print(f"⚠️ Replicación insuficiente ({success_count}/{majority})")
            return False

    async def _send_append_entries(self, session, peer, entry):
        """Envía una entrada individual a un seguidor"""
        try:
            async with session.post(f"{peer}/raft/append_entries", json={
                "term": self.current_term,
                "leader_id": self.node_id,
                "entry": entry.to_dict(),
            }, timeout=3) as resp:
                data = await resp.json()
                return data.get("success", False)
        except Exception:
            return False

    async def receive_append_entries(self, term: int, leader_id: str, entry: dict):
        """Seguidor recibe y aplica una entrada"""
        async with self._lock:
            if term < self.current_term:
                return {"term": self.current_term, "success": False}

            self.role = RaftRole.FOLLOWER
            self.leader_id = leader_id
            self.current_term = term
            self.reset_election_timer()

            log_entry = LogEntry.from_dict(entry)
            self.log.append(log_entry)
            self.commit_index = len(self.log)
            self.save_state()

            await self.apply_to_state_machine(log_entry)
            return {"term": self.current_term, "success": True}

    # ====================================================
    # Sincronización de nodos rezagados
    # ====================================================

    async def request_log_sync(self):
        """Seguidor solicita al líder las entradas que le faltan"""
        if not self.leader_id:
            return
        try:
            async with aiohttp.ClientSession(timeout=5) as session:
                async with session.get(f"{self.leader_id}/raft/sync?follower={self.node_id}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for e in data.get("missing_entries", []):
                            entry = LogEntry.from_dict(e)
                            self.log.append(entry)
                        self.save_state()
        except Exception:
            pass

    # ====================================================
    # Aplicación de commits
    # ====================================================

    async def apply_committed_entries(self):
        """Aplica todas las entradas confirmadas en orden"""
        while True:
            await asyncio.sleep(2)
            while self.last_applied < self.commit_index:
                self.last_applied += 1
                entry = self.log[self.last_applied - 1]
                await self.apply_to_state_machine(entry)

    async def apply_to_state_machine(self, entry: LogEntry):
        """Aplica la operación del log a la FSM local"""
        print(f"📥 [{self.node_id}] Aplicando entrada: {entry.command}")
        # Aquí cada nodo actualiza su base SQLite
