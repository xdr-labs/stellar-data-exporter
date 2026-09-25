#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TLS_DIR="$ROOT/.tls"
HOSTNAME_VALUE="${TLS_HOSTNAME:-$(hostname -s)}"
IP_VALUE="${TLS_IP:-$(hostname -I | awk '{print $1}')}"

mkdir -p "$TLS_DIR"
cat > "$TLS_DIR/openssl.cnf" <<EOF
[req]
distinguished_name = dn
x509_extensions = v3_req
prompt = no

[dn]
CN = ${HOSTNAME_VALUE}

[v3_req]
subjectAltName = @alt_names
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = ${HOSTNAME_VALUE}
DNS.2 = localhost
IP.1 = 127.0.0.1
IP.2 = ${IP_VALUE}
EOF

openssl req -x509 -nodes -newkey rsa:2048 \
  -days 365 \
  -keyout "$TLS_DIR/dev-server.key" \
  -out "$TLS_DIR/dev-server.crt" \
  -config "$TLS_DIR/openssl.cnf"

chmod 600 "$TLS_DIR/dev-server.key"
chmod 644 "$TLS_DIR/dev-server.crt"

echo "Created:"
echo "  $TLS_DIR/dev-server.crt"
echo "  $TLS_DIR/dev-server.key"
echo "SAN hostname: $HOSTNAME_VALUE"
echo "SAN IP:       $IP_VALUE"
