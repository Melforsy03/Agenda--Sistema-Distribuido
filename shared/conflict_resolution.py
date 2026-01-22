"""
Sistema de resolución de conflictos semántico para reconciliación de logs RAFT.

Proporciona detección y resolución de conflictos basada en semántica de operaciones,
con políticas determinísticas que garantizan convergencia en todos los nodos.
"""

import json
import hashlib
from enum import Enum
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass


class ConflictType(Enum):
    """Tipos de conflictos detectables"""
    NONE = "none"  # No hay conflicto
    DELETE_UPDATE = "delete_update"  # DELETE vs UPDATE
    UPDATE_UPDATE = "update_update"  # UPDATE vs UPDATE (mismo recurso)
    CREATE_CREATE = "create_create"  # CREATE duplicado
    DELETE_DELETE = "delete_delete"  # DELETE duplicado
    COMPATIBLE = "compatible"  # Operaciones compatibles


class ResolutionAction(Enum):
    """Acciones de resolución"""
    KEEP_FIRST = "keep_first"  # Mantener primera operación
    KEEP_SECOND = "keep_second"  # Mantener segunda operación
    KEEP_BOTH = "keep_both"  # Mantener ambas (compatible)
    MERGE = "merge"  # Fusionar operaciones
    DISCARD_BOTH = "discard_both"  # Descartar ambas


@dataclass
class OperationMetadata:
    """Metadatos extraídos de una operación"""
    operation_type: str  # CREATE_EVENT, UPDATE_EVENT, etc.
    resource_type: str  # event, group, user
    resource_id: Optional[str]  # ID del recurso afectado
    timestamp: float
    term: int
    node_id: str
    fields: List[str]  # Campos modificados
    raw_payload: dict


@dataclass
class Resolution:
    """Resultado de resolución de conflicto"""
    action: ResolutionAction
    winner: Optional[Any] = None  # LogEntry ganador
    merged: Optional[Any] = None  # LogEntry fusionado
    reason: str = ""  # Explicación de la decisión


class ConflictDetector:
    """Detecta conflictos semánticos entre operaciones de log"""
    
    def detect_conflicts(self, op1: Any, op2: Any) -> ConflictType:
        """
        Detecta si dos operaciones entran en conflicto
        
        Args:
            op1: Primera LogEntry
            op2: Segunda LogEntry
            
        Returns:
            Tipo de conflicto detectado
        """
        meta1 = self._extract_metadata(op1)
        meta2 = self._extract_metadata(op2)
        
        # Si operan sobre recursos diferentes, no hay conflicto
        if meta1.resource_id != meta2.resource_id:
            return ConflictType.NONE
        
        # Si IDs son None pero operaciones son iguales, verificar duplicado exacto
        if meta1.resource_id is None and meta2.resource_id is None:
            if op1.command == op2.command:
                return ConflictType.COMPATIBLE  # Duplicado exacto
            return ConflictType.NONE
        
        # Clasificar conflictos sobre el mismo recurso
        return self._classify_conflict(meta1.operation_type, meta2.operation_type)
    
    def _extract_metadata(self, op: Any) -> OperationMetadata:
        """Extrae metadatos semánticos de una operación"""
        try:
            data = json.loads(op.command)
        except (json.JSONDecodeError, AttributeError):
            # Fallback si command no es JSON válido
            return OperationMetadata(
                operation_type="UNKNOWN",
                resource_type="unknown",
                resource_id=None,
                timestamp=getattr(op, 'timestamp', 0),
                term=op.term,
                node_id=getattr(op, 'originating_node', ''),
                fields=[],
                raw_payload={}
            )
        
        operation_type = data.get("type", "UNKNOWN")
        payload = data.get("payload", {})
        op_upper = str(operation_type).upper()
        
        # Extraer ID del recurso
        resource_id = self._get_resource_id(op_upper, payload)
        resource_type = self._get_resource_type(op_upper, payload)
        
        # Extraer campos modificados
        excluded_keys = {"event_id", "eventId", "group_id", "groupId", "user_id", "userId", "resource_id", "resourceId", "id"}
        fields = [k for k in payload.keys() if k not in excluded_keys]
        
        return OperationMetadata(
            operation_type=operation_type,
            resource_type=resource_type,
            resource_id=resource_id,
            timestamp=getattr(op, 'timestamp', 0),
            term=op.term,
            node_id=getattr(op, 'originating_node', ''),
            fields=fields,
            raw_payload=payload
        )
    
    def _get_resource_id(self, op_upper: str, payload: dict) -> Optional[str]:
        """Extrae el ID del recurso según tipo de operación"""
        # Mapeo de operaciones a campos de ID, tolerando claves distintas según origen
        if "EVENT" in op_upper or "INVITATION" in op_upper:
            ext_id = payload.get("external_id")
            if ext_id:
                return f"event:{ext_id}"
            event_id = payload.get("event_id") or payload.get("eventId") or payload.get("id") or payload.get("resource_id")
            if event_id is not None:
                return f"event:{event_id}"
            # Fallback determinista para CREATE_* sin ID: hash de campos principales
            key_payload = {
                "title": payload.get("title"),
                "start_time": payload.get("start_time"),
                "end_time": payload.get("end_time"),
                "creator_id": payload.get("creator_id"),
                "group_id": payload.get("group_id"),
            }
            key_str = json.dumps(key_payload, sort_keys=True, default=str)
            key_hash = hashlib.sha1(key_str.encode("utf-8")).hexdigest()
            return f"event:{key_hash}"
        elif "GROUP" in op_upper:
            ext_id = payload.get("external_id")
            if ext_id:
                return f"group:{ext_id}"
            group_id = payload.get("group_id") or payload.get("groupId") or payload.get("id") or payload.get("resource_id")
            if group_id is not None:
                return f"group:{group_id}"
            # Fallback determinista: nombre del grupo (normalizado)
            name = payload.get("name") or payload.get("group_name")
            if name:
                return f"group_name:{name.strip().lower()}"
            return None
        elif "USER" in op_upper:
            user_id = payload.get("user_id") or payload.get("userId") or payload.get("username") or payload.get("id")
            return f"user:{user_id}" if user_id is not None else None
        
        # Si no se pudo inferir por el tipo, intentar con un id genérico
        generic_id = payload.get("id") or payload.get("resource_id") or payload.get("resourceId")
        generic_type = payload.get("resource_type")
        if generic_id is not None and generic_type:
            return f"{generic_type}:{generic_id}"
        
        return None
    
    def _get_resource_type(self, op_upper: str, payload: dict) -> str:
        """Determina el tipo de recurso desde el tipo de operación"""
        if "EVENT" in op_upper or payload.get("event_id") or payload.get("eventId"):
            return "event"
        elif "GROUP" in op_upper or payload.get("group_id") or payload.get("groupId"):
            return "group"
        elif "USER" in op_upper or payload.get("user_id") or payload.get("userId") or payload.get("username"):
            return "user"
        return payload.get("resource_type") or "unknown"
    
    def _classify_conflict(self, op1_type: str, op2_type: str) -> ConflictType:
        """Clasifica el tipo de conflicto entre dos operaciones"""
        op1_kind = self._operation_kind(op1_type)
        op2_kind = self._operation_kind(op2_type)

        # DELETE vs cualquier cosa
        if op1_kind == "delete" or op2_kind == "delete":
            if op1_kind == "delete" and op2_kind == "delete":
                return ConflictType.DELETE_DELETE
            elif op1_kind == "update" or op2_kind == "update":
                return ConflictType.DELETE_UPDATE
            # DELETE vs CREATE es imposible (DELETE requiere recurso existente)
            return ConflictType.COMPATIBLE
        
        # CREATE vs CREATE
        if op1_kind == "create" and op2_kind == "create":
            return ConflictType.CREATE_CREATE
        
        # UPDATE vs UPDATE
        if op1_kind == "update" and op2_kind == "update":
            return ConflictType.UPDATE_UPDATE
        
        # Otros casos son compatibles
        return ConflictType.COMPATIBLE

    def _operation_kind(self, op_type: str) -> str:
        """Normaliza el tipo de operación (create/update/delete)"""
        upper = (op_type or "").upper()
        if "DELETE" in upper or "CANCEL" in upper or "REMOVE" in upper:
            return "delete"
        if "CREATE" in upper or "ADD" in upper:
            return "create"
        if "UPDATE" in upper or "EDIT" in upper or "PATCH" in upper:
            return "update"
        return "other"


class ConflictResolver:
    """Resuelve conflictos aplicando políticas determinísticas"""
    
    def __init__(self):
        self.detector = ConflictDetector()
    
    def resolve(self, op1: Any, op2: Any) -> Resolution:
        """
        Resuelve conflicto entre dos operaciones según políticas
        
        Jerarquía de operaciones: DELETE > CREATE > UPDATE
        
        Args:
            op1: Primera LogEntry
            op2: Segunda LogEntry
            
        Returns:
            Resolution con resultado y explicación
        """
        conflict_type = self.detector.detect_conflicts(op1, op2)
        meta1 = self.detector._extract_metadata(op1)
        meta2 = self.detector._extract_metadata(op2)
        
        # Sin conflicto: mantener ambas
        if conflict_type == ConflictType.NONE:
            return Resolution(
                action=ResolutionAction.KEEP_BOTH,
                reason="Operaciones sobre recursos diferentes - sin conflicto"
            )
        
        # Regla 1: DELETE siempre gana (jerarquía más alta)
        if conflict_type == ConflictType.DELETE_UPDATE:
            if "DELETE" in meta1.operation_type:
                return Resolution(
                    action=ResolutionAction.KEEP_FIRST,
                    winner=op1,
                    reason="DELETE tiene prioridad sobre UPDATE (jerarquía)"
                )
            else:
                return Resolution(
                    action=ResolutionAction.KEEP_SECOND,
                    winner=op2,
                    reason="DELETE tiene prioridad sobre UPDATE (jerarquía)"
                )
        
        # Regla 2: DELETE duplicado - deduplicar
        if conflict_type == ConflictType.DELETE_DELETE:
            return Resolution(
                action=ResolutionAction.KEEP_FIRST,
                winner=op1,
                reason="DELETE duplicado - deduplicación (idempotente)"
            )
        
        # Regla 3: CREATE duplicado - temporal gana
        if conflict_type == ConflictType.CREATE_CREATE:
            if meta1.timestamp < meta2.timestamp:
                return Resolution(
                    action=ResolutionAction.KEEP_FIRST,
                    winner=op1,
                    reason=f"CREATE más antiguo gana (timestamp: {meta1.timestamp} < {meta2.timestamp})"
                )
            elif meta2.timestamp < meta1.timestamp:
                return Resolution(
                    action=ResolutionAction.KEEP_SECOND,
                    winner=op2,
                    reason=f"CREATE más antiguo gana (timestamp: {meta2.timestamp} < {meta1.timestamp})"
                )
            else:
                # Desempate por node_id
                winner = self._tie_breaker(op1, op2, meta1, meta2)
                return Resolution(
                    action=ResolutionAction.KEEP_FIRST if winner == op1 else ResolutionAction.KEEP_SECOND,
                    winner=winner,
                    reason=f"CREATE temporal empate - desempate por node_id ({winner.originating_node})"
                )
        
        # Regla 4: UPDATE vs UPDATE
        if conflict_type == ConflictType.UPDATE_UPDATE:
            # Verificar si pueden fusionarse (campos diferentes)
            if self._can_merge(meta1, meta2):
                merged = self._merge_updates(op1, op2, meta1, meta2)
                return Resolution(
                    action=ResolutionAction.MERGE,
                    merged=merged,
                    reason=f"UPDATEs fusionados (campos: {meta1.fields} + {meta2.fields})"
                )
            
            # Mismo campo: Last-Write-Wins
            if meta1.timestamp > meta2.timestamp:
                return Resolution(
                    action=ResolutionAction.KEEP_FIRST,
                    winner=op1,
                    reason=f"UPDATE LWW (timestamp: {meta1.timestamp} > {meta2.timestamp})"
                )
            elif meta2.timestamp > meta1.timestamp:
                return Resolution(
                    action=ResolutionAction.KEEP_SECOND,
                    winner=op2,
                    reason=f"UPDATE LWW (timestamp: {meta2.timestamp} > {meta1.timestamp})"
                )
            else:
                # Desempate por node_id
                winner = self._tie_breaker(op1, op2, meta1, meta2)
                return Resolution(
                    action=ResolutionAction.KEEP_FIRST if winner == op1 else ResolutionAction.KEEP_SECOND,
                    winner=winner,
                    reason=f"UPDATE LWW empate - desempate por node_id ({winner.originating_node})"
                )
        
        # Compatible: mantener ambas
        return Resolution(
            action=ResolutionAction.KEEP_BOTH,
            reason=f"Operaciones compatibles ({meta1.operation_type}, {meta2.operation_type})"
        )
    
    def _can_merge(self, meta1: OperationMetadata, meta2: OperationMetadata) -> bool:
        """Determina si dos UPDATEs pueden fusionarse (modifican campos diferentes)"""
        fields1 = set(meta1.fields)
        fields2 = set(meta2.fields)
        
        # Si no hay intersección, se pueden fusionar
        return len(fields1 & fields2) == 0
    
    def _merge_updates(self, op1: Any, op2: Any, meta1: OperationMetadata, meta2: OperationMetadata) -> Any:
        """Fusiona dos UPDATEs sobre campos diferentes"""
        # Importar aquí para evitar dependencia circular
        from shared.raft import LogEntry
        
        # Fusionar payloads
        merged_payload = {**meta1.raw_payload, **meta2.raw_payload}
        
        # Crear entrada fusionada con timestamp más reciente
        merged_entry = LogEntry(
            term=max(op1.term, op2.term),
            command=json.dumps({"type": meta1.operation_type, "payload": merged_payload}),
            timestamp=max(meta1.timestamp, meta2.timestamp),
            originating_node=f"merged"
        )
        
        return merged_entry
    
    def _tie_breaker(self, op1: Any, op2: Any, meta1: OperationMetadata, meta2: OperationMetadata) -> Any:
        """Desempate determinístico cuando timestamps son iguales"""
        # Criterio 1: Node ID (extraer número del ID)
        node1_priority = self._extract_priority(meta1.node_id)
        node2_priority = self._extract_priority(meta2.node_id)
        
        if node1_priority != node2_priority:
            return op1 if node1_priority > node2_priority else op2
        
        # Criterio 2: Término RAFT
        if meta1.term != meta2.term:
            return op1 if meta1.term > meta2.term else op2
        
        # Criterio 3: Hash del comando (determinístico)
        hash1 = hashlib.sha256(op1.command.encode()).hexdigest()
        hash2 = hashlib.sha256(op2.command.encode()).hexdigest()
        
        return op1 if hash1 > hash2 else op2
    
    def _extract_priority(self, node_id: str) -> int:
        """Extrae prioridad numérica del ID del nodo"""
        if not node_id:
            return 0
        
        # Extraer dígitos del node_id
        digits = ''.join(filter(str.isdigit, node_id))
        return int(digits) if digits else 0
