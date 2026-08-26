#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
umask 077

apt-get update
apt-get -y -o Dpkg::Options::=--force-confold upgrade
apt-get install -y wireguard-tools ufw unattended-upgrades curl iptables powerdns powerdns-recursor pdns-backend-sqlite3

cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

cat >/etc/apt/apt.conf.d/52unattended-upgrades-local <<'EOF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-WithUsers "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
EOF

systemctl enable --now apt-daily.timer apt-daily-upgrade.timer

cat >/etc/sysctl.d/99-wireguard-forward.conf <<'EOF'
net.ipv4.ip_forward=1
EOF

sysctl --system

install -d -m 700 /etc/wireguard
install -d -m 700 /etc/wireguard/users

PUBLIC_IP="$(
    curl -4fsS --max-time 5 \
        http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address \
    || curl -4fsS --max-time 10 https://api.ipify.org
)"

WAN_IF="$(ip -4 route show default | awk '{print $5; exit}')"

wg genkey >/etc/wireguard/host.key
wg pubkey </etc/wireguard/host.key >/etc/wireguard/host.pub

HOST_PRIV="$(cat /etc/wireguard/host.key)"
HOST_PUB="$(cat /etc/wireguard/host.pub)"

cat >/etc/wireguard/wg0.conf <<EOF
[Interface]
Address = 10.67.69.1/24
ListenPort = 2026
PrivateKey = ${HOST_PRIV}
EOF

for i in $(seq 2 20); do
    USER="/etc/wireguard/users/user-${i}"

    wg genkey >"${USER}.key"
    wg pubkey <"${USER}.key" >"${USER}.pub"

    USER_PRIV="$(cat "${USER}.key")"
    USER_PUB="$(cat "${USER}.pub")"

    cat >>/etc/wireguard/wg0.conf <<EOF

[Peer]
PublicKey = ${USER_PUB}
AllowedIPs = 10.67.69.${i}/32
EOF

    cat >"${USER}.conf" <<EOF
[Interface]
PrivateKey = ${USER_PRIV}
Address = 10.67.69.${i}/32

[Peer]
PublicKey = ${HOST_PUB}
Endpoint = ${PUBLIC_IP}:2026
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
EOF

    cat >"${USER}.wg.conf" <<EOF
[Interface]
PrivateKey = ${USER_PRIV}

[Peer]
PublicKey = ${HOST_PUB}
Endpoint = ${PUBLIC_IP}:2026
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
EOF
done

chmod 600 /etc/wireguard/wg0.conf
chmod 600 /etc/wireguard/host.key /etc/wireguard/host.pub
chmod 600 /etc/wireguard/users/*

cp /etc/ufw/before.rules /etc/ufw/before.rules.orig

{
    cat <<EOF
*nat
:POSTROUTING ACCEPT [0:0]
-A POSTROUTING -s 10.67.69.0/24 -o ${WAN_IF} -j MASQUERADE
COMMIT

EOF
    cat /etc/ufw/before.rules.orig
} >/etc/ufw/before.rules

WAN_IF="$(ip -4 route show default | awk '{print $5; exit}')"

# PowerDNS API: source-restricted to the VPN VM (10.67.69.2) only; token
# auth on top (consumed by caddy DNS-01 in tigor-ai docker-compose.yml).
cat >>/etc/ufw/before.rules <<EOF

*filter
:PDNSAPI - [0:0]
-A PDNSAPI -s 10.67.69.2 -p tcp --dport 8081 -j ACCEPT
-A PDNSAPI -j DROP
-I INPUT 1 -j PDNSAPI
COMMIT

EOF

ufw default deny incoming
ufw default allow outgoing
ufw default deny routed

ufw allow 22/tcp
ufw allow 2026/udp

ufw allow in on wg0 from 10.67.69.0/24 to 10.67.69.1 proto tcp port 22
ufw allow in on wg0 from 10.67.69.0/24 to 10.67.69.1 proto udp port 53
ufw route allow in on wg0 out on wg0 from 10.67.69.0/24 to 10.67.69.2
ufw route allow in on wg0 out on "${WAN_IF}" from 10.67.69.2 to 0.0.0.0/0

# --- PowerDNS: authoritative for ai.tgr.rs / vpn.tgr.rs (ACME DNS-01) ---
# The public tgr.rs zone stays at unlimited.rs; these subdomains are
# delegated here (NS records at unlimited.rs, done outside this script).
# Caddy obtains wildcard certs by writing _acme-challenge TXT records via
# the API (8081, token-auth, source-restricted to 10.67.69.2).
install -d -m 750 /etc/powerdns
install -d -m 750 /etc/powerdns-recursor

PDNS_API_TOKEN="$(wg genkey)"

# authoritative on 127.0.0.1:5300 (recursor owns :53); the API listens on
# the wg0 IP so the caddy container (10.67.69.2) can reach it over the VPN
# — ufw before.rules drops 8081 from anywhere but 10.67.69.2, token on top.
cat >/etc/powerdns/powerdns.conf <<EOF
local-address=127.0.0.1
local-port=5300
setuid=pdns
launch=sqlite3
sqlite3-ds=/var/lib/powerdns/powerdns.db
webserver=yes
webserver-address=10.67.69.1
webserver-port=8081
webserver-allow-from=10.67.69.2
api=yes
api-key=${PDNS_API_TOKEN}
EOF

# recursor: answers the VPN only. Only the delegated subdomains are served
# locally; the rest of tgr.rs goes upstream.
# API: 10.67.69.1:8081 (token auth, source-restricted to 10.67.69.2).
cat >/etc/powerdns-recursor/recursor.conf <<EOF
local-address=10.67.69.1
allow-from=10.67.69.0/24
forward-zones=ai.tgr.rs=127.0.0.1#5300, vpn.tgr.rs=127.0.0.1#5300
max-cache-size=1000
EOF

pdns-util --config-name=root --root-sername=root --root-serpassword=root create-pdns sqlite3
systemctl enable --now pdns pdns-recursor
for z in ai.tgr.rs vpn.tgr.rs; do
    pdns-util zone-info "$z" >/dev/null 2>&1 || \
        pdns-util create-zone "$z" --nameserver ns1.tgr.rs. --soa-serial 1
    pdns-util change-record "$z" "${PUBLIC_IP}" A >/dev/null || true
done

# persist the API token for the caddy container (source into tigor-ai .env)
echo "PDNS_API_TOKEN=${PDNS_API_TOKEN}" >/root/pdns-api-token.env
chmod 600 /root/pdns-api-token.env

ufw --force enable

systemctl enable --now wg-quick@wg0

sync
systemctl reboot
