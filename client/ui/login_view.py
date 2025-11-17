import streamlit as st

def show_login_page(api_client):
    st.title("📅 Sistema de Agenda - Login")

    if "show_register" not in st.session_state:
        st.session_state.show_register = False

    if not st.session_state.show_register:
        # --- LOGIN ---
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")

        if st.button("Iniciar sesión"):
            # Eliminar espacios en blanco al inicio y final
            username = username.strip()
            password = password.strip()

            # Validaciones en el cliente
            if not username or not password:
                st.error("❌ Por favor, ingresa usuario y contraseña")
            elif len(username) < 3:
                st.error("❌ El usuario debe tener al menos 3 caracteres")
            elif len(password) < 3:
                st.error("❌ La contraseña debe tener al menos 3 caracteres")
            else:
                try:
                    result = api_client.login(username, password)
                    
                    # Verificar que el resultado tenga los campos esperados
                    if not result or "token" not in result or "user_id" not in result:
                        st.error("❌ Error: Respuesta del servidor inválida")
                        return
                    
                    token = result["token"]
                    user_id = result["user_id"]

                    # Guardar en session state
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.user_id = user_id
                    st.session_state.session_token = token
                    st.session_state.websocket_connected = False

                    # Agregar token y user_id a query params para persistencia
                    st.query_params['session_token'] = token
                    st.query_params['user_id'] = str(user_id)

                    st.success("✅ Sesión iniciada correctamente")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ {str(e)}")

        if st.button("Crear cuenta nueva"):
            st.session_state.show_register = True
            st.rerun()

    else:
        # --- REGISTRO ---
        username = st.text_input("Nuevo usuario")
        password = st.text_input("Nueva contraseña", type="password")

        if st.button("Registrarse"):
            # Eliminar espacios en blanco al inicio y final
            username = username.strip()
            password = password.strip()

            # Validaciones en el cliente
            if not username or not password:
                st.error("❌ Usuario y contraseña no pueden estar vacíos")
            elif len(username) < 3:
                st.error("❌ El usuario debe tener al menos 3 caracteres")
            elif len(password) < 3:
                st.error("❌ La contraseña debe tener al menos 3 caracteres")
            elif ' ' in username:
                st.error("❌ El usuario no puede contener espacios")
            else:
                try:
                    result = api_client.register(username, password)
                    st.success("✅ Usuario creado exitosamente. Ahora puedes iniciar sesión")
                    st.session_state.show_register = False
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ {str(e)}")

        if st.button("Ya tengo cuenta"):
            st.session_state.show_register = False
            st.rerun()