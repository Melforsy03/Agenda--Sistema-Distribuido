# 📅 Agenda Distribuida

Proyecto de **agenda colaborativa** con autenticación, grupos (jerárquicos o no), gestión de eventos y detección de conflictos de horarios.  
Construido con **Streamlit + SQLite**, organizado en capas (`database/`, `services/`, `ui/`).

---

## 🚀 Características

- Autenticación de usuarios (registro y login con contraseña hasheada).
- Creación de **eventos personales** y **grupales**.
- **Detección automática de conflictos** en agendas.
- Gestión de **grupos jerárquicos** y **no jerárquicos**.
- Invitaciones a grupos con aceptación/rechazo.
- Visualización de calendario con interfaz moderna (`streamlit-calendar`).

---

## 📦 Requisitos

- Python **3.9+**
- [pip](https://pip.pypa.io/en/stable/) o [conda](https://docs.conda.io/) para instalar dependencias.

---

## 🔧 Instalación

1. Clona el repositorio o copia los archivos:
   ```bash
   git clone https://github.com/tu-usuario/agenda_distribuida.git
   cd agenda_distribuida
