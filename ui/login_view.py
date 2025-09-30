import streamlit as st
from services.auth_service import AuthService

def show_login_page():
    auth = AuthService()

    st.title("📅 Sistema de Agenda - Login")

    if "show_register" not in st.session_state:
        st.session_state.show_register = False

    if not st.session_state.show_register:
        # --- LOGIN ---
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")

        if st.button("Iniciar sesión"):
            if auth.login(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success("✅ Sesión iniciada")
                st.rerun()
            else:
                st.error("❌ Usuario o contraseña incorrectos")

        if st.button("Crear cuenta nueva"):
            st.session_state.show_register = True
            st.rerun()

    else:
        # --- REGISTRO ---
        username = st.text_input("Nuevo usuario")
        password = st.text_input("Nueva contraseña", type="password")

        if st.button("Registrarse"):
            if auth.register(username, password):
                st.success("✅ Usuario creado, ahora inicia sesión")
                st.session_state.show_register = False
                st.rerun()
            else:
                st.error("❌ Ese usuario ya existe")

        if st.button("Ya tengo cuenta"):
            st.session_state.show_register = False
            st.rerun()
