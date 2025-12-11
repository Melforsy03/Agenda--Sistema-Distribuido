# Ver logs en tiempo real
docker compose logs -f

# Ver logs de un servicio específico
docker compose logs backend
docker compose logs frontend

# Ver recursos usados
docker compose top

# Ver imágenes creadas
docker images 

//////////////////

# 1️⃣ Primera vez (o después de cambios)
docker compose up --build

# 2️⃣ Si necesitas parar para hacer otras cosas
docker compose stop

# 3️⃣ Para reanudar (sin rebuild)
docker compose start

# 4️⃣ Si cambiaste el código
docker compose down
docker compose up --build

# 5️⃣ Para apagar completamente
docker compose down