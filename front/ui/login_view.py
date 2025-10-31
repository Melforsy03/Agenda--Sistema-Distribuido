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

            try:
                result = api_client.login(username, password)
                token = result["token"]
                user_id = result["user_id"]

                # Guardar en session state
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.user_id = user_id
                st.session_state.session_token = token

                # Agregar token a query params para persistencia
                st.query_params['session_token'] = token

                # Mark WebSocket as not yet connected (will connect in main app)
                st.session_state.websocket_connected = False

                st.success("✅ Sesión iniciada")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al iniciar sesión: {str(e)}")

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

            if not username or not password:
                st.error("❌ Usuario y contraseña no pueden estar vacíos")
            else:
                try:
                    result = api_client.register(username, password)
                    st.success("✅ Usuario creado, ahora inicia sesión")
                    st.session_state.show_register = False
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al crear usuario: {str(e)}")

        if st.button("Ya tengo cuenta"):
            st.session_state.show_register = False
            st.rerun()