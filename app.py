import streamlit as st
import database as db
from datetime import datetime
from streamlit_calendar import calendar as st_calendar

# Asegura que la base de datos y las tablas existen antes de cualquier consulta
db.setup_database()

def show_login_page():
    """Muestra la página de inicio de sesión y registro con diseño mejorado."""
    # Configuración de la página
    st.set_page_config(
        page_title="Sistema de Agenda - Login",
        page_icon="📅",
        layout="centered"
    )
    
    # Header principal
    st.markdown("""
    <div style='text-align: center; padding: 2rem 0;'>
        <h1 style='color: #1f77b4; margin-bottom: 0;'>📅 Sistema de Agenda</h1>
        <p style='color: #666; font-size: 1.2rem; margin-top: 0.5rem;'>Gestiona tus eventos y colabora con tu equipo</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")

    # Inicializar el estado de la vista si no existe
    if "show_register" not in st.session_state:
        st.session_state.show_register = False

    # Contenedor centrado
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        if not st.session_state.show_register:
            # Vista de Login
            st.markdown("### 🔐 Iniciar Sesión")
            st.markdown("Bienvenido de vuelta, inicia sesión para continuar")
            
            with st.form("login_form"):
                login_username = st.text_input(
                    "👤 Nombre de Usuario", 
                    key="login_username",
                    placeholder="Ingresa tu usuario"
                )
                login_password = st.text_input(
                    "🔒 Contraseña", 
                    type="password", 
                    key="login_password",
                    placeholder="Ingresa tu contraseña"
                )
                
                login_button = st.form_submit_button(
                    "🚀 Iniciar Sesión", 
                    use_container_width=True
                )

                if login_button:
                    if login_username and login_password:
                        if db.Database().check_password(login_username, login_password):
                            st.session_state["logged_in"] = True
                            st.session_state["username"] = login_username
                            st.success("✅ ¡Sesión iniciada correctamente!")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("❌ Nombre de usuario o contraseña incorrectos.")
                    else:
                        st.warning("⚠️ Por favor, completa todos los campos.")
            
            # Enlace para ir al registro
            st.markdown("---")
            st.markdown(
                "<div style='text-align: center;'>¿No tienes una cuenta?</div>", 
                unsafe_allow_html=True
            )
            if st.button("📝 Crear cuenta nueva", use_container_width=True):
                st.session_state.show_register = True
                st.rerun()
        
        else:
            # Vista de Registro
            st.markdown("### 📝 Crear Cuenta")
            st.markdown("Únete a nuestro sistema de agenda")
            
            with st.form("register_form"):
                register_username = st.text_input(
                    "👤 Nombre de Usuario", 
                    key="register_username",
                    placeholder="Elige un nombre de usuario"
                )
                register_password = st.text_input(
                    "🔒 Contraseña", 
                    type="password", 
                    key="register_password",
                    placeholder="Crea una contraseña segura"
                )
                
                register_button = st.form_submit_button(
                    "🎯 Registrarse", 
                    use_container_width=True
                )

                if register_button:
                    if register_username and register_password:
                        # Validaciones básicas
                        if len(register_username) < 3:
                            st.error("❌ El nombre de usuario debe tener al menos 3 caracteres.")
                        elif len(register_password) < 4:
                            st.error("❌ La contraseña debe tener al menos 4 caracteres.")
                        else:
                            if db.Database().add_user(register_username, register_password):
                                st.success("✅ ¡Usuario registrado exitosamente!")
                                st.info("Ahora puedes iniciar sesión con tu nueva cuenta.")
                                st.balloons()
                                # Cambiar automáticamente a la vista de login
                                st.session_state.show_register = False
                                st.rerun()
                            else:
                                st.error("❌ El nombre de usuario ya existe. Prueba con otro.")
                    else:
                        st.warning("⚠️ Por favor, completa todos los campos para registrarte.")
            
            # Enlace para volver al login
            st.markdown("---")
            st.markdown(
                "<div style='text-align: center;'>¿Ya tienes una cuenta?</div>", 
                unsafe_allow_html=True
            )
            if st.button("🔐 Iniciar sesión", use_container_width=True):
                st.session_state.show_register = False
                st.rerun()
    
    # Footer informativo
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666; font-size: 0.9rem;'>
        <p>💡 <strong>Características del sistema:</strong></p>
        <p>• Gestión de eventos personales y grupales • Detección de conflictos de horario • Grupos jerárquicos y no jerárquicos</p>
    </div>
    """, unsafe_allow_html=True)

def show_calendar_view(user_id):
    """Muestra la vista del calendario."""
    st.header("📅 Tu Calendario")
    
    # Obtener los eventos del usuario para el calendario
    events_db = db.Database().get_events_by_user(user_id)
    calendar_events = []
    if events_db:
        for event in events_db:
            # El componente de calendario espera un formato específico
            calendar_events.append({
                "title": event[0],
                "start": event[2],
                "end": event[3],
                "resourceId": "a"
            })
    
    calendar_options = {
        "headerToolbar": {
            "left": "today prev,next",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek,timeGridDay",
        },
        "slotMinTime": "08:00:00",
        "slotMaxTime": "20:00:00",
        "initialView": "dayGridMonth"
    }
    
    # Mostrar el calendario
    st_calendar(events=calendar_events, options=calendar_options, key="calendar1")

def show_create_event_view(user_id):
    """Muestra la vista para crear eventos."""
    st.header("➕ Crear Nuevo Evento")
    
    with st.form("event_form"):
        col1, col2 = st.columns([2, 1])
        
        with col1:
            title = st.text_input("📝 Título del Evento", placeholder="Ej: Reunión de equipo")
            description = st.text_area("📄 Descripción", placeholder="Detalles del evento...")
        
        with col2:
            is_group_event = st.checkbox("👥 Evento grupal")
        
        # Fechas y horas
        st.markdown("### 🕐 Horario del Evento")
        col_start, col_end = st.columns(2)
        with col_start:
            st.markdown("**Inicio**")
            start_date = st.date_input("Fecha de Inicio", key="start_date")
            start_time = st.time_input("Hora de Inicio", key="start_time")
        with col_end:
            st.markdown("**Finalización**")
            end_date = st.date_input("Fecha de Fin", key="end_date")
            end_time = st.time_input("Hora de Fin", key="end_time")
        
        start_datetime_str = f"{start_date} {start_time}"
        end_datetime_str = f"{end_date} {end_time}"
        
        # Participantes
        if is_group_event:
            st.markdown("### 🏢 Selección de Grupo")
            group_id = None
            participants_ids = []
            
            groups = db.Database().get_groups_by_user(user_id)
            if groups:
                group_options = {f"{g[1]} ({'Jerárquico' if g[2] else 'No Jerárquico'})": g[0] for g in groups}
                selected_group_name = st.selectbox(
                    "🏢 Elige el grupo para el evento", 
                    options=list(group_options.keys()),
                    help="Todos los miembros del grupo seleccionado participarán en el evento"
                )
                if selected_group_name:
                    group_id = group_options[selected_group_name]
                    participants = db.Database().get_group_members(group_id)
                    participants_ids = [p[0] for p in participants]
                    
                    # Mostrar miembros del grupo
                    member_names = [p[1] for p in participants]
                    st.success(f"✅ Participantes del evento: {', '.join(member_names)}")
            else:
                st.warning("⚠️ No tienes grupos creados. Ve a la sección de Gestión de Grupos para crear uno.")
        else:
            st.markdown("### 👤 Selección de Participantes")
            group_id = None
            all_users = db.Database().get_all_users()
            user_options = {user[1]: user[0] for user in all_users if user[0] != user_id}
            selected_participants = st.multiselect(
                "👤 Selecciona participantes individuales (opcional)", 
                options=list(user_options.keys()),
                help="Puedes invitar a usuarios específicos a este evento personal"
            )
            participants_ids = [user_options[p] for p in selected_participants]

        submit_event_button = st.form_submit_button("🎯 Crear Evento", use_container_width=True)
        
        if submit_event_button:
            if title and start_datetime_str and end_datetime_str:
                try:
                    start_dt = datetime.strptime(start_datetime_str, '%Y-%m-%d %H:%M:%S')
                    end_dt = datetime.strptime(end_datetime_str, '%Y-%m-%d %H:%M:%S')
                    
                    if start_dt >= end_dt:
                        st.error("⚠️ La hora de fin debe ser posterior a la de inicio.")
                    else:
                        if db.Database().check_conflict(user_id, start_datetime_str, end_datetime_str):
                            st.error("❌ ¡Conflicto de horario! Ya tienes un evento programado en ese periodo.")
                        else:
                            conflicts = [p_id for p_id in participants_ids if db.Database().check_conflict(p_id, start_datetime_str, end_datetime_str)]
                            
                            if conflicts:
                                conflict_usernames = [db.Database().get_username(p_id) for p_id in conflicts]
                                st.error(f"❌ ¡Conflicto de horario! Los siguientes participantes no están disponibles: {', '.join(conflict_usernames)}")
                            else:
                                event_id = db.Database().add_event(
                                    title=title,
                                    description=description,
                                    start_time=start_datetime_str,
                                    end_time=end_datetime_str,
                                    creator_id=user_id,
                                    group_id=group_id,
                                    is_group_event=is_group_event
                                )
                                all_participants = participants_ids + [user_id]
                                for p_id in all_participants:
                                    db.Database().add_participant_to_event(event_id, p_id)
                                st.success("✅ ¡Evento creado exitosamente!")
                                st.balloons()
                                st.rerun()
                except ValueError:
                    st.error("❌ Formato de fecha/hora inválido. Asegúrate de seleccionar ambos.")
            else:
                st.error("❌ Por favor, completa todos los campos requeridos.")

def show_edit_group_view(user_id, group_id):
    """Muestra la vista de edición de un grupo específico."""
    if not group_id:
        st.error("❌ Error: No se especificó un grupo para editar.")
        return
    
    # Verificar que el usuario es el creador del grupo
    if not db.Database().is_group_creator(user_id, group_id):
        st.error("❌ No tienes permisos para editar este grupo.")
        return
    
    # Obtener información del grupo
    group_details = db.Database().get_group_details(group_id)
    if not group_details:
        st.error("❌ Grupo no encontrado.")
        return
    
    # Header con botón de regresar
    col_back, col_title = st.columns([1, 4])
    with col_back:
        if st.button("← Regresar", key="back_to_groups"):
            st.session_state["current_view"] = None
            if "editing_group_id" in st.session_state:
                del st.session_state["editing_group_id"]
            st.rerun()
    
    with col_title:
        st.header(f"⚙️ Editar Grupo: {group_details[1]}")
    
    st.markdown("---")
    
    # Sección 1: Información del grupo
    st.subheader("📝 Información del Grupo")
    with st.form("edit_group_info"):
        new_name = st.text_input("Nombre del grupo", value=group_details[1])
        new_description = st.text_area("Descripción", value=group_details[2] or "")
        
        if st.form_submit_button("💾 Guardar Información", use_container_width=True):
            if new_name:
                if db.Database().update_group_info(group_id, new_name, new_description):
                    st.success("✅ Información del grupo actualizada.")
                    st.rerun()
                else:
                    st.error("❌ Error al actualizar el grupo.")
            else:
                st.warning("⚠️ El nombre del grupo no puede estar vacío.")
    
    st.markdown("---")
    
    # Sección 2: Gestión de miembros con opción de invitar integrada
    st.subheader("👥 Gestión de Miembros")
    
    # Mostrar miembros actuales
    members = db.Database().get_group_members(group_id)
    if members:
        st.markdown("**Miembros actuales:**")
        for member in members:
            col_member, col_action = st.columns([3, 1])
            with col_member:
                role = "👑 Creador" if member[0] == user_id else "👤 Miembro"
                st.markdown(f"• {member[1]} ({role})")
            with col_action:
                if member[0] != user_id:  # No permitir que el creador se remueva a sí mismo
                    if st.button("🗑️", key=f"remove_{member[0]}", help="Remover del grupo"):
                        if db.Database().remove_user_from_group(member[0], group_id):
                            st.success(f"✅ {member[1]} ha sido removido del grupo.")
                            st.rerun()
                        else:
                            st.error(f"❌ Error al remover a {member[1]}.")
    
    # Invitar nuevos miembros (integrado en la misma sección)
    st.markdown("**📧 Invitar Nuevos Miembros:**")
    
    all_users = db.Database().get_all_users()
    current_member_ids = [m[0] for m in members]
    available_users = {user[1]: user[0] for user in all_users 
                     if user[0] not in current_member_ids}
    
    if available_users:
        with st.form("invite_new_members"):
            col_select, col_button = st.columns([3, 1])
            
            with col_select:
                # Usar session state para limpiar el campo después de enviar
                invite_key = f"edit_new_members_{group_id}"
                if f"clear_{invite_key}" in st.session_state and st.session_state[f"clear_{invite_key}"]:
                    st.session_state[invite_key] = []
                    st.session_state[f"clear_{invite_key}"] = False
                
                new_members = st.multiselect("Selecciona usuarios para invitar", 
                                           options=list(available_users.keys()),
                                           key=invite_key,
                                           placeholder="Elige usuarios...")
            
            with col_button:
                st.markdown("<br>", unsafe_allow_html=True)  # Espaciado para alinear el botón
                if st.form_submit_button("📧 Invitar", use_container_width=True):
                    if new_members:
                        invited_count = 0
                        for member_username in new_members:
                            member_id = available_users[member_username]
                            if db.Database().invite_user_to_group(group_id, member_id, user_id):
                                invited_count += 1
                        
                        if invited_count > 0:
                            st.success(f"✅ Se enviaron {invited_count} invitaciones.")
                            # Marcar para limpiar el campo en el próximo rerun
                            st.session_state[f"clear_{invite_key}"] = True
                            st.rerun()
                        else:
                            st.error("❌ Error al enviar invitaciones.")
                    else:
                        st.warning("⚠️ Selecciona al menos un usuario para invitar.")
    else:
        st.info("📭 No hay usuarios disponibles para invitar.")


def show_groups_view(user_id):
    """Muestra la vista de gestión de grupos."""
    st.header("👥 Gestión de Grupos")
    
    # Crear nuevo grupo
    with st.expander("🆕 Crear Nuevo Grupo", expanded=True):
        st.info("💡 Crea un grupo para organizar eventos colaborativos.")
        
        with st.form("group_form"):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                group_name = st.text_input("🏷️ Nombre del Grupo", placeholder="Ej: Equipo de Marketing")
                group_description = st.text_area("📝 Descripción", placeholder="Describe el propósito del grupo...")
            
            with col2:
                is_hierarchical = st.checkbox("⚡ Grupo jerárquico", help="La cita se acepta inmediatamente sin votación")
            
            all_users = db.Database().get_all_users()
            user_options = {user[1]: user[0] for user in all_users if user[0] != user_id}
            selected_members = st.multiselect("👤 Selecciona miembros", options=list(user_options.keys()))
            
            add_group_button = st.form_submit_button("🎯 Crear Grupo", use_container_width=True)
            
            if add_group_button:
                if group_name and selected_members:
                    group_id = db.Database().add_group(group_name, group_description, is_hierarchical, user_id)
                    if group_id:
                        # Para los miembros seleccionados, enviar invitaciones
                        invited_count = 0
                        for member_username in selected_members:
                            member_id = user_options[member_username]
                            if db.Database().invite_user_to_group(group_id, member_id, user_id):
                                invited_count += 1
                        
                        st.success(f"✅ Grupo '{group_name}' creado exitosamente.")
                        if invited_count > 0:
                            st.info(f"📧 Se enviaron {invited_count} invitaciones. Los usuarios deben aceptarlas para unirse al grupo.")
                        st.rerun()
                    else:
                        st.error("❌ El nombre del grupo ya existe.")
                else:
                    st.warning("⚠️ Por favor, completa todos los campos.")
    
    # Mostrar grupos existentes
    st.markdown("### 📋 Mis Grupos")
    groups = db.Database().get_groups_by_user(user_id)
    
    if groups:
        for i, group in enumerate(groups):
            group_id, group_name, is_hierarchical = group
            
            # Verificar si el usuario es el creador del grupo
            is_creator = db.Database().is_group_creator(user_id, group_id)
            
            with st.expander(f"🏢 {group_name} {'⭐ (Creador)' if is_creator else ''}", expanded=False):
                # Información básica del grupo
                group_details = db.Database().get_group_details(group_id)
                if group_details:
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.markdown(f"**Nombre:** {group_details[1]}")
                        if group_details[2]:
                            st.markdown(f"**Descripción:** {group_details[2]}")
                        st.markdown(f"**Tipo:** {'⚡ Jerárquico' if group_details[3] else '🗳️ No Jerárquico'}")
                        st.markdown(f"**Creador:** {group_details[5]}")
                    
                    with col2:
                        members = db.Database().get_group_members(group_id)
                        st.markdown(f"**👥 Miembros ({len(members)}):**")
                        for member in members:
                            st.markdown(f"• {member[1]}")
                
                # Opciones de edición (solo para creadores)
                if is_creator:
                    st.markdown("---")
                    col_edit, col_delete = st.columns([3, 1])
                    with col_edit:
                        if st.button(f"⚙️ Editar Grupo", key=f"edit_btn_{group_id}", use_container_width=True):
                            st.session_state["editing_group_id"] = group_id
                            st.session_state["current_view"] = "edit_group"
                            st.rerun()
                    with col_delete:
                        if st.button(f"🗑️ Eliminar", key=f"delete_btn_{group_id}", use_container_width=True, type="secondary"):
                            st.session_state["deleting_group_id"] = group_id
                
                # Opción para salir del grupo (para miembros no creadores)
                elif not is_creator:
                    st.markdown("---")
                    if st.button(f"🚪 Salir del grupo", key=f"leave_{group_id}", type="secondary"):
                        if db.Database().remove_user_from_group(user_id, group_id):
                            st.success("✅ Has salido del grupo exitosamente.")
                            st.rerun()
                        else:
                            st.error("❌ Error al salir del grupo.")
    else:
        st.info("📭 Aún no perteneces a ningún grupo.")

def show_agenda_page():
    """Muestra la página principal de la agenda con navegación lateral."""
    # Configuración de la página
    st.set_page_config(
        page_title="Sistema de Agenda",
        page_icon="📅",
        layout="wide"
    )
    
    user_id = db.Database().get_user_id(st.session_state.username)
    
    # Sidebar para navegación
    with st.sidebar:
        st.title(f"👋 ¡Hola, {st.session_state.username}!")
        st.markdown("---")
        
        # Menú de navegación con botones
        st.markdown("### 🧭 Navegación")
        
        # Inicializar la opción del menú si no existe
        if "menu_option" not in st.session_state:
            st.session_state.menu_option = "📅 Ver Calendario"
        
        # Botones de navegación
        if st.button("📅 Ver Calendario", use_container_width=True, 
                    type="primary" if st.session_state.menu_option == "📅 Ver Calendario" else "secondary"):
            st.session_state.menu_option = "📅 Ver Calendario"
            st.rerun()
            
        if st.button("➕ Crear Evento", use_container_width=True,
                    type="primary" if st.session_state.menu_option == "➕ Crear Evento" else "secondary"):
            st.session_state.menu_option = "➕ Crear Evento"
            st.rerun()
            
        if st.button("👥 Gestión de Grupos", use_container_width=True,
                    type="primary" if st.session_state.menu_option == "👥 Gestión de Grupos" else "secondary"):
            st.session_state.menu_option = "👥 Gestión de Grupos"
            st.rerun()

        # Botón de invitaciones con indicador
        pending_invitations = db.Database().get_pending_invitations(user_id)
        invitations_count = len(pending_invitations) if pending_invitations else 0
        invitations_label = f"📧 Invitaciones ({invitations_count})" if invitations_count > 0 else "📧 Invitaciones"
        button_type = "primary" if (st.session_state.menu_option == "📧 Invitaciones" or invitations_count > 0) else "secondary"
        
        if st.button(invitations_label, use_container_width=True, type=button_type):
            st.session_state.menu_option = "📧 Invitaciones"
            st.rerun()
        
        menu_option = st.session_state.menu_option
        
        st.markdown("---")
        
        # Resumen rápido
        with st.container():
            st.markdown("### 📊 Resumen")
            events = db.Database().get_events_by_user(user_id)
            groups = db.Database().get_groups_by_user(user_id)
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Eventos", len(events) if events else 0)
            with col2:
                st.metric("Grupos", len(groups) if groups else 0)
        
        st.markdown("---")
        
        # Botón de cerrar sesión
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = None
            st.rerun()
    
    # Contenido principal basado en la selección del menú
    if "current_view" in st.session_state and st.session_state["current_view"] == "edit_group":
        show_edit_group_view(user_id, st.session_state.get("editing_group_id"))
    elif menu_option == "📅 Ver Calendario":
        show_calendar_view(user_id)
    elif menu_option == "➕ Crear Evento":
        show_create_event_view(user_id)
    elif menu_option == "👥 Gestión de Grupos":
        show_groups_view(user_id)
    elif menu_option == "📧 Invitaciones":
        show_invitations_view(user_id)

def show_invitations_view(user_id):
    """Muestra la vista de invitaciones pendientes."""
    st.header("📧 Invitaciones de Grupo")
    
    pending_invitations = db.Database().get_pending_invitations(user_id)
    
    if pending_invitations:
        st.markdown(f"### ✉️ Tienes {len(pending_invitations)} invitación(es) pendiente(s)")
        
        for invitation in pending_invitations:
            invitation_id, group_name, inviter_name, created_at, group_id = invitation
            
            with st.container():
                # Información de la invitación
                st.markdown(f"""
                <div style='background-color: #2d3339; padding: 1.5rem; border-radius: 0.75rem; margin-bottom: 1rem; border-left: 5px solid #1f77b4; border: 1px solid #404040;'>
                    <h4 style='margin: 0 0 0.5rem 0; color: #1f77b4;'>🏢 {group_name}</h4>
                    <p style='margin: 0; color: #e6e6e6;'><strong>Invitado por:</strong> {inviter_name}</p>
                    <p style='margin: 0; color: #e6e6e6;'><strong>Fecha:</strong> {created_at}</p>
                </div>
                """, unsafe_allow_html=True)
                
                # Botones de acción
                col1, col2, col3 = st.columns([1, 1, 2])
                
                with col1:
                    if st.button(f"✅ Aceptar", key=f"accept_{invitation_id}", use_container_width=True):
                        if db.Database().respond_to_invitation(invitation_id, 'accepted', user_id):
                            st.success(f"¡Te has unido al grupo '{group_name}'!")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("Error al aceptar la invitación.")
                
                with col2:
                    if st.button(f"❌ Rechazar", key=f"decline_{invitation_id}", use_container_width=True):
                        if db.Database().respond_to_invitation(invitation_id, 'declined', user_id):
                            st.success("Invitación rechazada.")
                            st.rerun()
                        else:
                            st.error("Error al rechazar la invitación.")
                
                st.markdown("---")
    else:
        st.info("📬 No tienes invitaciones pendientes.")
        st.markdown("""
        <div style='text-align: center; padding: 2rem; color: #b3b3b3;'>
            <h3>🎉 ¡Todo al día!</h3>
            <p>Cuando alguien te invite a un grupo, las invitaciones aparecerán aquí.</p>
        </div>
        """, unsafe_allow_html=True)

# --- Lógica principal de la aplicación ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["username"] = None

if st.session_state.logged_in:
    show_agenda_page()
else:
    show_login_page()