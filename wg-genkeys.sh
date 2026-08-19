#!/usr/bin/env bash

set -euo pipefail
umask 077

VPN_DIR="${VPN_DIR:-./vpns}"
SERVER_HOST="${SERVER_HOST:-vpn.example.com}"
SERVER_PORT="${SERVER_PORT:-2026}"
VPN_NETWORK="${VPN_NETWORK:-10.67.69}"
VPN_PREFIX="${VPN_PREFIX:-24}"
SERVER_ADDRESS="${VPN_NETWORK}.1"
VM_ADDRESS="${VPN_NETWORK}.2"

mkdir -p "$VPN_DIR"

for peer in server vm; do
  wg genkey | tee "$VPN_DIR/$peer.key" | wg pubkey > "$VPN_DIR/$peer.pub"
done

SERVER_PRIVATE_KEY="$(<"$VPN_DIR/server.key")"
SERVER_PUBLIC_KEY="$(<"$VPN_DIR/server.pub")"
VM_PRIVATE_KEY="$(<"$VPN_DIR/vm.key")"
VM_PUBLIC_KEY="$(<"$VPN_DIR/vm.pub")"

cat > "$VPN_DIR/server.conf" <<EOF
[Interface]
PrivateKey = $SERVER_PRIVATE_KEY
Address = $SERVER_ADDRESS/$VPN_PREFIX
ListenPort = $SERVER_PORT

[Peer]
PublicKey = $VM_PUBLIC_KEY
AllowedIPs = $VM_ADDRESS/32
EOF

cat > "$VPN_DIR/vm.conf" <<EOF
[Interface]
PrivateKey = $VM_PRIVATE_KEY
Address = $VM_ADDRESS/$VPN_PREFIX
Table = off

[Peer]
PublicKey = $SERVER_PUBLIC_KEY
Endpoint = $SERVER_HOST:$SERVER_PORT
AllowedIPs = $SERVER_ADDRESS/32
PersistentKeepalive = 25
EOF

chmod 600 "$VPN_DIR"/*

printf 'Created %s and %s\n' "$VPN_DIR/server.conf" "$VPN_DIR/vm.conf"
