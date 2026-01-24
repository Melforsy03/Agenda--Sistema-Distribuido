#!/bin/bash
# Genera certificados autofirmados para desarrollo
# Uso: ./generate_certs.sh [directorio_destino]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CERTS_DIR="${1:-${PROJECT_DIR}/certs}"
DAYS_VALID=365
KEY_SIZE=2048

# Crear directorio si no existe
mkdir -p "$CERTS_DIR"

# Nombre del host (puedes cambiarlo por tu dominio o IP)
COMMON_NAME="${COMMON_NAME:-agenda.local}"

# Obtener IP local para incluir en SAN
LOCAL_IP=$(hostname -I | awk '{print $1}')

SUBJECT="/C=US/ST=Development/L=Local/O=AgendaDistribuida/OU=Dev/CN=${COMMON_NAME}"

echo "🔐 Generando certificados TLS autofirmados..."
echo "   Directorio: $CERTS_DIR"
echo "   Common Name: $COMMON_NAME"
echo "   IP Local: $LOCAL_IP"
echo "   Validez: $DAYS_VALID días"
echo ""

# 1. Generar clave privada
echo "📝 Generando clave privada (${KEY_SIZE} bits)..."
openssl genrsa -out "$CERTS_DIR/server.key" $KEY_SIZE 2>/dev/null

# 2. Crear archivo de extensiones para SAN (Subject Alternative Names)
# Esto es necesario para que navegadores modernos acepten el certificado
cat > "$CERTS_DIR/openssl_ext.cnf" << EOF
[req]
default_bits = ${KEY_SIZE}
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = v3_req

[dn]
C = US
ST = Development
L = Local
O = AgendaDistribuida
OU = Dev
CN = ${COMMON_NAME}

[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${COMMON_NAME}
DNS.2 = localhost
DNS.3 = *.${COMMON_NAME}
DNS.4 = coordinator
DNS.5 = frontend_a
DNS.6 = traefik
IP.1 = 127.0.0.1
IP.2 = ::1
IP.3 = ${LOCAL_IP}
EOF

# 3. Generar CSR y certificado autofirmado en un solo paso
echo "📝 Generando certificado autofirmado..."
openssl req -new -x509 \
    -key "$CERTS_DIR/server.key" \
    -out "$CERTS_DIR/server.crt" \
    -days $DAYS_VALID \
    -config "$CERTS_DIR/openssl_ext.cnf" \
    -extensions v3_req \
    2>/dev/null

# 4. Establecer permisos seguros
chmod 600 "$CERTS_DIR/server.key"
chmod 644 "$CERTS_DIR/server.crt"

# Limpiar archivos temporales
rm -f "$CERTS_DIR/openssl_ext.cnf"

echo ""
echo "✅ Certificados generados exitosamente:"
echo "   🔑 Clave privada: $CERTS_DIR/server.key"
echo "   📜 Certificado:   $CERTS_DIR/server.crt"
echo ""
echo "📋 Verificación del certificado:"
openssl x509 -in "$CERTS_DIR/server.crt" -noout -subject -dates -ext subjectAltName 2>/dev/null || \
openssl x509 -in "$CERTS_DIR/server.crt" -noout -subject -dates
echo ""
echo "⚠️  NOTA: Este es un certificado autofirmado."
echo "   Los navegadores mostrarán una advertencia de seguridad."
echo "   Para producción, usa Let's Encrypt o un CA válido."
echo ""
echo "🔧 Para agregar a tu sistema (opcional, evita advertencias):"
echo "   sudo cp $CERTS_DIR/server.crt /usr/local/share/ca-certificates/agenda.crt"
echo "   sudo update-ca-certificates"
