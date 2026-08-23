#!/usr/bin/env bash
set -euo pipefail
# Run from inside the VM — verifies all traffic is confined to the WireGuard tunnel.
# Usage: ssh root@vm ./tests/01_network-isolation.sh

FAIL=0

check() {
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "PASS: $desc"
    else
        echo "FAIL: $desc"
        FAIL=1
    fi
}

# --- 1. Default route goes through WG interface ---
check "default route uses wg interface" \
    grep -qE '^\s*default\s+via\s+\S+\s+dev\s+wg' /proc/net/route

# --- 2. No routes bypass WG (except loopback) ---
# /proc/net/route columns: dst, gateway, dev, flags
non_wg_routes=$(awk -F'\t' '$3 != "lo" && $3 !~ /^wg/' /proc/net/route 2>/dev/null || true)
if [[ -z "$non_wg_routes" ]]; then
    echo "PASS: no non-WG/lo routes in routing table"
else
    echo "FAIL: non-WG routes found: $non_wg_routes"
    FAIL=1
fi

# --- 3. WG interface is up ---
check "wg interface is UP" \
    grep -qE '^wg\S+\s+.*state UP' /proc/net/wireguard 2>/dev/null || \
    ip -br link show | grep -qE '^wg\S+\s+UP'

# --- 4. Cannot reach host WG endpoint directly (10.67.69.1) ---
# The host should be reachable only through the tunnel for allowed services.
# A raw ping to the host WG IP should NOT succeed (blocked by firewall).
check "cannot ping host WG IP 10.67.69.1" \
    ! ping -c1 -W2 10.67.69.1

# --- 5. No non-WG interfaces exist (except lo, vsock if any) ---
# The VM should only have lo, a WG device, and the virtio-net (backed by passt/WG).
# Any ethX/ensX with its own gateway is a red flag.
other_gw_ifaces=$(awk -F'\t' '$2 != 0 && $3 !~ /^wg/ && $3 != "lo"' /proc/net/route 2>/dev/null | cut -f3 | sort -u || true)
if [[ -z "$other_gw_ifaces" ]]; then
    echo "PASS: no non-WG interfaces with gateways"
else
    echo "FAIL: interfaces with non-WG gateways: $other_gw_ifaces"
    FAIL=1
fi

# --- 6. ip_forward is disabled (VM must not route for others) ---
fwd=$(cat /proc/sys/net/ipv4/ip_forward 2>/dev/null || echo 0)
if [[ "$fwd" == "0" ]]; then
    echo "PASS: ip_forward disabled"
else
    echo "FAIL: ip_forward=$fwd (should be 0)"
    FAIL=1
fi

exit $FAIL
