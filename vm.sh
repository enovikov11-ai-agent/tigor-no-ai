#!/usr/bin/env bash
set -Eeuo pipefail

# ── knobs: 1:1 with vm.xsl <vm> attributes ──
VM_NAME="${VM_NAME:-hermes}"
VM_CPU="${VM_CPU:-64}"
VM_RAM="${VM_RAM:-128}"
VM_KERNEL="${VM_KERNEL:-/ssd/vm/vm-r17-nvda-pods-vsock-BOOTX64.efi}"
VM_GPU="${VM_GPU:-true}"
VM_VSOCK="${VM_VSOCK:-true}"
VM_UI="${VM_UI:-true}"
# ── <mount> src:dst[:ro] ──
MOUNT_0="${MOUNT_0:-/ssd/internet:/ssd/internet:ro}"
MOUNT_1="${MOUNT_1:-/hdd/internet/kiwix:/hdd/internet/kiwix:ro}"
MOUNT_2="${MOUNT_2:-/hdd/internet/wikipedia:/hdd/internet/wikipedia:ro}"
MOUNT_3="${MOUNT_3:-/ssd/vm/hermes:/ssd/vm/hermes:}"
MOUNT_4="${MOUNT_4:-/ssd/telegraf/hermes:/ssd/telegraf/host:}"
# ── <disk> src ──
DISK="${DISK:-/ssd/vm/${VM_NAME}.qcow2}"
# ── <net> bus ──
NET_BUS="${NET_BUS:-0x04}"

cleanup() { kill 0 2>/dev/null || true; ip netns del "ns-${VM_NAME}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

# WireGuard namespace
ip netns add "ns-${VM_NAME}"
ip link add "wg-${VM_NAME}" type wireguard
wg setconf "wg-${VM_NAME}" "/ssd/vm/ns-wg-${VM_NAME}.conf"
ip link set "wg-${VM_NAME}" netns "ns-${VM_NAME}"
ip -n "ns-${VM_NAME}" addr add 10.67.69.2/24 dev "wg-${VM_NAME}"
ip -n "ns-${VM_NAME}" link set "wg-${VM_NAME}" up
ip -n "ns-${VM_NAME}" route add default via 10.67.69.1 dev "wg-${VM_NAME}"

# passt
rm -f "/run/${VM_NAME}-passt.sock"
ip netns exec "ns-${VM_NAME}" passt --foreground --vhost-user \
  --socket "/run/${VM_NAME}-passt.sock" --repair-path none \
  --interface "wg-${VM_NAME}" --outbound-if4 "wg-${VM_NAME}" \
  --ipv4-only --mtu 1420 --address 10.67.69.2 --netmask 24 \
  --gateway 10.67.69.1 --no-map-gw --map-host-loopback none \
  --map-guest-addr none --tcp-ports all --udp-ports all &

for _ in {1..100}; do [[ -S "/run/${VM_NAME}-passt.sock" ]] && break; sleep 0.01; done

# virtiofsd + QEMU fs args
FS_ARGS=""
for i in 0 1 2 3 4; do
  IFS=':' read -r src dst ro <<< "${!MOUNT_${i}}"
  sock="/run/${VM_NAME}-fs-${i}.sock"
  rm -f "$sock"
  if [[ -n "${ro:-}" ]]; then
    virtiofsd --socket-path="$sock" --shared-dir="$src" --readonly &
  else
    virtiofsd --socket-path="$sock" --shared-dir="$src" &
  fi
  for _ in {1..100}; do [[ -S "$sock" ]] && break; sleep 0.01; done
  FS_ARGS+=" -chardev socket,id=fs${i},path=${sock} -device vhost-user-fs-pci,chardev=fs${i},tag=${dst}"
done

# GPU vfio
GPU_ARGS=""
if [[ "$VM_GPU" == "true" ]]; then
  GPU_ARGS=" -object iommufd,id=iommufd0 -device vfio-pci,host=0000:41:00.0,iommufd=iommufd0 -device vfio-pci,host=0000:41:00.1,iommufd=iommufd0"
fi

# QEMU
exec qemu-system-x86_64 \
  -nodefaults -no-user-config \
  -machine pc-q35-10.2,memory-backend=ram,usb=off,vmport=off,smm=off,dump-guest-core=off \
  -accel kvm \
  -cpu host,migratable=off \
  -object memory-backend-memfd,id=ram,size=${VM_RAM}G,share=on,hugetlb=on,hugetlbsize=1G \
  -smp ${VM_CPU} \
  -rtc base=utc \
  -drive if=pflash,format=raw,readonly=on,file=/run/libvirt/nix-ovmf/edk2-x86_64-code.fd \
  -kernel ${VM_KERNEL} \
  -sandbox on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny \
  -object rng-random,id=rng,filename=/dev/urandom \
  -device virtio-rng-pci,rng=rng \
  -display none \
  $( [[ "$VM_VSOCK" == "true" ]] && echo "-device vhost-vsock-pci,guest-cid=auto" ) \
  -serial stdio -monitor none \
  -drive file=${DISK},if=virtio,format=qcow2,discard=unmap \
  ${GPU_ARGS} \
  -chardev socket,id=net0,path="/run/${VM_NAME}-passt.sock" \
  -netdev vhost-user,chardev=net0,id=net \
  -device virtio-net-pci,netdev=net,mac=52:54:00:a9:f5:da,romfile=,addr=0x0,bus=pcie.${NET_BUS#0x} \
  ${FS_ARGS}
