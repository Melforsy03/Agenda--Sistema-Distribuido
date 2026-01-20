"""
Extensión del módulo RAFT con reconciliación semántica de conflictos.

Este módulo agrega al final de shared/raft.py el nuevo método de reconciliación.
"""

async def _reconcile_from_peer_semantic(self, peer: str):
    """Trae entradas que el peer tenga y el líder no, con resolución semántica de conflictos.
    
    Detecta conflictos sobre el mismo recurso y aplica políticas determinísticas:
    - DELETE > CREATE > UPDATE (jerarquía de operaciones)
    - UPDATEs sobre campos diferentes se fusionan  
    - Last-Write-Wins para UPDATEs del mismo campo
    """
    if not self.is_leader():
        return
    
    # Importar módulo de resolución de conflictos
    try:
        from shared.conflict_resolution import ConflictDetector, ConflictResolver, ResolutionAction
        use_semantic = True
    except ImportError:
        logger.warning("Módulo conflict_resolution no disponible - usando reconciliación simple")
        use_semantic = False
    
    try:
        # 1. Obtener log completo del peer
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(f"{peer}/raft/log/full") as resp:
                if resp.status != 200:
                    return
                data = await resp.json()
                peer_entries_data = data.get("entries", [])
    except Exception as e:
        logger.warning(f"Error obteniendo log completo de {peer}: {e}")
        return

    if not peer_entries_data:
        return

    # 2. Convertir a LogEntry objects
    peer_entries = []
    for entry_data in peer_entries_data:
        entry = LogEntry.from_dict(entry_data)
        peer_entries.append(entry)

    # 3. Detectar entradas que no están en nuestro log
    existing_keys = {(e.term, e.command) for e in self.log}
    new_peer_entries = []
    
    for peer_entry in peer_entries:
        key = (peer_entry.term, peer_entry.command)
        if key not in existing_keys:
            new_peer_entries.append(peer_entry)

    if not new_peer_entries:
        logger.debug(f"Reconciliación con {peer}: sin entradas nuevas")
        return

    # Si no tenemos resolución semántica, usar método simple
    if not use_semantic:
        for entry in new_peer_entries:
            entry.index = len(self.log) + 1
            self.log.append(entry)
            self.commit_index = max(self.commit_index, entry.index)
            self.last_applied = self.commit_index
            self.save_state()
            await self.apply_to_state_machine(entry)
            await self.replicate_log(entry)
        return

    # 4. Resolución semántica de conflictos
    detector = ConflictDetector()
    resolver = ConflictResolver()
    
    resolved_entries = []
    processed_peer_indices = set()
    
    for peer_entry in new_peer_entries:
        # Buscar conflictos con el log local
        conflict_found = False
        
        for local_entry in self.log:
            conflict_type = detector.detect_conflicts(local_entry, peer_entry)
            
            if conflict_type.value != "none":
                # Hay conflicto - resolver
                resolution = resolver.resolve(local_entry, peer_entry)
                
                logger.info(f"🔧 Conflicto detectado: {conflict_type.value}")
                logger.info(f"   Resolución: {resolution.action.value} - {resolution.reason}")
                
                if resolution.action == ResolutionAction.KEEP_FIRST:
                    # Mantener entrada local, descartar peer
                    processed_peer_indices.add(id(peer_entry))
                    conflict_found = True
                    break
                
                elif resolution.action == ResolutionAction.KEEP_SECOND:
                    # Preferir peer, agregar
                    resolved_entries.append(peer_entry)
                    processed_peer_indices.add(id(peer_entry))
                    conflict_found = True
                    break
                
                elif resolution.action == ResolutionAction.MERGE:
                    # Fusionar ambas
                    resolved_entries.append(resolution.merged)
                    processed_peer_indices.add(id(peer_entry))
                    conflict_found = True
                    break
                
                elif resolution.action == ResolutionAction.KEEP_BOTH:
                    # Son compatibles, mantener ambas
                    continue
        
        # Si no hubo conflictos, agregar entrada del peer
        if not conflict_found and id(peer_entry) not in processed_peer_indices:
            resolved_entries.append(peer_entry)

    # 5. Incorporar entradas resueltas al log
    if not resolved_entries:
        logger.debug(f"Reconciliación con {peer}: todos los conflictos resueltos sin nuevas entradas")
        return

    logger.info(f"🔄 Reconciliando {len(resolved_entries)} entradas desde {peer}")
    
    for entry in resolved_entries:
        # Asignar nuevo índice
        entry.index = len(self.log) + 1
        # Asegurar que tiene timestamp
        if not hasattr(entry, 'timestamp') or entry.timestamp is None:
            entry.timestamp = time.time()
        # Asegurar origen si no tiene
        if not hasattr(entry, 'originating_node') or entry.originating_node is None:
            entry.originating_node = peer
        
        # Agregar al log
        self.log.append(entry)
        self.commit_index = max(self.commit_index, entry.index)
        self.last_applied = self.commit_index
        self.save_state()
        
        # Aplicar al estado local
        await self.apply_to_state_machine(entry)
        
        # Replicar al resto de peers
        await self.replicate_log(entry)

    logger.info(f"✅ Reconciliación semántica completada: {len(resolved_entries)} entradas agregadas")
