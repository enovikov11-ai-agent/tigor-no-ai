#!/usr/bin/env bash
set -Eeuo pipefail

VM_NAME="hermes"

cleanup() {
    trap - EXIT INT TERM

    kill $(jobs -pr) 2>/dev/null || true
    wait 2>/dev/null || true

    ip netns del "ns-${VM_NAME}" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

setup_wg() {
    ip netns del "ns-${VM_NAME}" 2>/dev/null || true
    ip link del "wg-${VM_NAME}" 2>/dev/null || true

    ip netns add "ns-${VM_NAME}"
    ip link add "wg-${VM_NAME}" type wireguard
    wg setconf "wg-${VM_NAME}" "/ssd/vm/ns-wg-${VM_NAME}.conf"
    ip link set "wg-${VM_NAME}" netns "ns-${VM_NAME}"

    ip -n "ns-${VM_NAME}" addr add 10.67.69.2/24 dev "wg-${VM_NAME}"
    ip -n "ns-${VM_NAME}" link set "wg-${VM_NAME}" up
    ip -n "ns-${VM_NAME}" route add default via 10.67.69.1 dev "wg-${VM_NAME}"
}

wait_socket() {
    local socket=$1

    for _ in {1..100}; do
        [[ -S "$socket" ]] && return
        sleep 0.01
    done

    echo "socket did not appear: $socket" >&2
    return 1
}

start_passt() {
    rm -f "/run/${VM_NAME}-passt.sock"

    ip netns exec "ns-${VM_NAME}" passt \
        --foreground \
        --vhost-user \
        --socket "/run/${VM_NAME}-passt.sock" \
        --repair-path none \
        --interface "wg-${VM_NAME}" \
        --outbound-if4 "wg-${VM_NAME}" \
        --ipv4-only \
        --mtu 1420 \
        --address 10.67.69.2 \
        --netmask 24 \
        --gateway 10.67.69.1 \
        --no-map-gw \
        --map-host-loopback none \
        --map-guest-addr none \
        --tcp-ports all \
        --udp-ports all &
    
    wait_socket "/run/${VM_NAME}-passt.sock"
}

start_virtiofsd() {
    rm -f "/run/${VM_NAME}-internet.sock"

    virtiofsd \
        --socket-path="/run/${VM_NAME}-internet.sock" \
        --shared-dir=/ssd/internet \
        --readonly &
    
    wait_socket "/run/${VM_NAME}-internet.sock"
}

run_qemu() {
    qemu-system-x86_64 \
        -nodefaults \
        -no-user-config \
        -machine pc-q35-10.2,memory-backend=ram,usb=off,vmport=off,smm=off,dump-guest-core=off \
        -accel kvm \
        -cpu host,migratable=off \
        -object memory-backend-memfd,id=ram,size=256G,share=on \
        -smp 128 \
        -rtc base=utc \
        -drive if=pflash,format=raw,readonly=on,file=/run/libvirt/nix-ovmf/edk2-x86_64-code.fd \
        -kernel /ssd/vm/vm-r18-rc1-nvda-pods-vsock-BOOTX64.efi \
        -sandbox on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny \
        -object rng-random,id=rng,filename=/dev/urandom \
        -device virtio-rng-pci,rng=rng \
        -display none \
        -device vhost-vsock-pci,guest-cid=3 \
        -serial stdio \
        -monitor none \
        -drive file="/ssd/vm/${VM_NAME}.qcow2",if=virtio,format=qcow2,discard=unmap \
        -device vfio-pci,host=0000:41:00.0 \
        -device vfio-pci,host=0000:41:00.1 \
        -chardev socket,id=net0,path="/run/${VM_NAME}-passt.sock" \
        -netdev vhost-user,chardev=net0,id=net \
        -device virtio-net-pci,netdev=net,mac=52:54:00:a9:f5:da,romfile= \
        -chardev socket,id=fs0,path="/run/${VM_NAME}-internet.sock" \
        -device vhost-user-fs-pci,chardev=fs0,tag=/ssd/internet
}

setup_wg
start_passt
start_virtiofsd
run_qemu
