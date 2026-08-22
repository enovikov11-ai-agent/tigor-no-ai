#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
umask 077

# Update system
apt-get update
apt-get -y -o Dpkg::Options::=--force-confold upgrade

# Packages
apt-get install -y wireguard-tools ufw unattended-upgrades curl iptables

# Daily unattended upgrades
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

# IPv4 forwarding
cat >/etc/sysctl.d/99-wireguard-forward.conf <<'EOF'
net.ipv4.ip_forward=1
EOF

sysctl --system

# WireGuard directories
install -d -m 700 /etc/wireguard
install -d -m 700 /etc/wireguard/users

# Detect public IP and Internet-facing interface
PUBLIC_IP="$(
    curl -4fsS --max-time 5 \
        http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address \
    || curl -4fsS --max-time 10 https://api.ipify.org
)"

WAN_IF="$(ip -4 route show default | awk '{print $5; exit}')"

# Host keypair
wg genkey >/etc/wireguard/host.key
wg pubkey </etc/wireguard/host.key >/etc/wireguard/host.pub

HOST_PRIV="$(cat /etc/wireguard/host.key)"
HOST_PUB="$(cat /etc/wireguard/host.pub)"

# Server config
cat >/etc/wireguard/wg0.conf <<EOF
[Interface]
Address = 10.67.69.1/24
ListenPort = 2026
PrivateKey = ${HOST_PRIV}
EOF

# Users 10.67.69.2 - 10.67.69.20
for i in $(seq 2 20); do
    USER="/etc/wireguard/users/user-${i}"

    wg genkey >"${USER}.key"
    wg pubkey <"${USER}.key" >"${USER}.pub"

    USER_PRIV="$(cat "${USER}.key")"
    USER_PUB="$(cat "${USER}.pub")"

    # Server peer
    cat >>/etc/wireguard/wg0.conf <<EOF

[Peer]
PublicKey = ${USER_PUB}
AllowedIPs = 10.67.69.${i}/32
EOF

    # wg-quick client config
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

    # Plain "wg setconf" config: Interface contains only PrivateKey
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

# Persistent NAT through UFW
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

# Firewall:
# - protect VPS input
# - keep SSH accessible
# - allow WireGuard UDP/2026
# - do not firewall routed VPN traffic
ufw default deny incoming
ufw default allow outgoing
ufw default allow routed
ufw allow 22/tcp
ufw allow 2026/udp
ufw --force enable

# Start WireGuard and enable on boot
systemctl enable --now wg-quick@wg0

sync
systemctl reboot
