#!/usr/bin/env bash
set -euo pipefail
# Run from inside the VM — verifies SSH access to host (10.67.69.1) is denied.
# Usage: ssh root@vm ./tests/03_no_ssh_to_host.sh

FAIL=0
HOST_WG_IP="10.67.69.1"

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

check_fail() {
    local desc="$1"
    shift
    if ! "$@" >/dev/null 2>&1; then
        echo "PASS: $desc"
    else
        echo "FAIL: $desc"
        FAIL=1
    fi
}

# --- 1. SSH port 22 on host is not reachable ---
check_fail "cannot connect to host:22 via SSH" \
    timeout 5 bash -c "echo >/dev/tcp/${HOST_WG_IP}/22"

# --- 2. NCat/netcat to host:22 fails ---
check_fail "netcat to host:22 refused/timeout" \
    timeout 5 nc -zvw4 "${HOST_WG_IP}" 22 2>/dev/null

# --- 3. No SSH keys for host exist in the VM ---
known_hosts=$(cat ~/.ssh/known_hosts 2>/dev/null || true)
if [[ -z "$known_hosts" ]] || ! echo "$known_hosts" | grep -q "$HOST_WG_IP"; then
    echo "PASS: no known_hosts entry for ${HOST_WG_IP}"
else
    echo "FAIL: known_hosts contains ${HOST_WG_IP}"
    FAIL=1
fi

# --- 4. No SSH config allows host access ---
ssh_config=$(cat ~/.ssh/config 2>/dev/null || true)
if echo "$ssh_config" | grep -qiE "(host|hostname)\s+.*${HOST_WG_IP//./\\.}"; then
    echo "FAIL: SSH config references ${HOST_WG_IP}"
    FAIL=1
else
    echo "PASS: no SSH config for ${HOST_WG_IP}"
fi

# --- 5. No SSH agent forwarding to host ---
if [[ -n "${SSH_AUTH_SOCK:-}" ]]; then
    echo "WARN: SSH_AUTH_SOCK is set — check agent forwarding"
else
    echo "PASS: no SSH agent socket (agent forwarding off)"
fi

exit $FAIL
