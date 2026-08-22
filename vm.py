#!/usr/bin/env python3

vms = {
    "hermes": {
        "cpu": 64,
        "ram": 128,
        "kernel": "/ssd/vm/vm-r37-nvda-pods-vsock-BOOTX64.efi",
        "gpu": True,
        "vsock": True,
        "ui": True,
        "net_bus": "0x04",
        "disk": "/ssd/vm/hermes.qcow2",
        "mounts": [
            {"src": "/ssd/internet", "dst": "/ssd/internet", "readonly": True},
            {"src": "/hdd/internet/kiwix", "dst": "/hdd/internet/kiwix", "readonly": True},
            {"src": "/hdd/internet/wikipedia", "dst": "/hdd/internet/wikipedia", "readonly": True},
            {"src": "/ssd/vm/hermes", "dst": "/ssd/vm/hermes"},
            {"src": "/ssd/telegraf/hermes", "dst": "/ssd/telegraf/host"},
        ],
    },
}


for name, config in vms.items():
    script = f"""#!/usr/bin/env bash
set -Eeuo pipefail

cleanup() {{
    trap - EXIT INT TERM

    kill $(jobs -pr) 2>/dev/null || true
    wait 2>/dev/null || true

    ip netns del ns-{name} 2>/dev/null || true
}}

trap cleanup EXIT INT TERM

ip netns del "ns-{VM_NAME}" 2>/dev/null || true
ip link del "wg-{name}" 2>/dev/null || true

ip netns add "ns-{name}"
ip link add "wg-{name}" type wireguard
wg setconf "wg-{name}" "/ssd/vm/ns-wg-{name}.conf"
ip link set "wg-{name}" netns "ns-{name}"

ip -n "ns-{name}" addr add 10.67.69.2/24 dev "wg-{name}"
ip -n "ns-{name}" link set "wg-{name}" up
ip -n "ns-{name}" route add default via 10.67.69.1 dev "wg-{name}"

wait_socket() {{
    local socket=$1

    for _ in {{1..100}}; do
        [[ -S "$socket" ]] && return
        sleep 0.01
    done

    echo "socket did not appear: $socket" >&2
    return 1
}}

rm -f "/run/{name}-passt.sock"

ip netns exec "ns-{name}" passt \
    --foreground \
    --vhost-user \
    --socket "/run/{name}-passt.sock" \
    --repair-path none \
    --interface "wg-{name}" \
    --outbound-if4 "wg-{name}" \
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

wait_socket "/run/{name}-passt.sock"

"""

    fs_args = []
    for i, m in enumerate(c["mounts"]):
        fs = f"/run/{name}-fs-{i}.sock"
        ro = " --readonly" if m.get("readonly") else ""
        s += f'rm -f "{fs}"\n'
        s += f'virtiofsd --socket-path="{fs}" --shared-dir={m["src"]}{ro} &\n'
        s += f'for _ in {{1..100}}; do [[ -S "{fs}" ]] && break; sleep 0.01; done\n'
        fs_args.append(f"-chardev socket,id=fs{i},path={fs}")
        fs_args.append(f"-device vhost-user-fs-pci,chardev=fs{i},tag={m['dst']}")
    s += '\n'
    bus = c["net_bus"][2:]
    s += f"""exec qemu-system-x86_64 \\
  -nodefaults -no-user-config \\
  -machine pc-q35-10.2,memory-backend=ram,usb=off,vmport=off,smm=off,dump-guest-core=off \\
  -accel kvm \\
  -cpu host,migratable=off \\
  -object memory-backend-memfd,id=ram,size={c["ram"]}G,share=on,hugetlb=on,hugetlbsize=1G \\
  -smp {c["cpu"]} \\
  -rtc base=utc \\
  -drive if=pflash,format=raw,readonly=on,file=/run/libvirt/nix-ovmf/edk2-x86_64-code.fd \\
  -kernel {c["kernel"]} \\
  -sandbox on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny \\
  -object rng-random,id=rng,filename=/dev/urandom \\
  -device virtio-rng-pci,rng=rng \\
  -display none \\
"""
    if c["vsock"]:
        s += '  -device vhost-vsock-pci,guest-cid=auto \\\n'
    s += f"""  -serial stdio -monitor none \\
  -drive file={c["disk"]},if=virtio,format=qcow2,discard=unmap \\
"""
    if c["gpu"]:
        s += """  -object iommufd,id=iommufd0 \\
  -device vfio-pci,host=0000:41:00.0,iommufd=iommufd0 \\
  -device vfio-pci,host=0000:41:00.1,iommufd=iommufd0 \\
"""
    s += f"""  -chardev socket,id=net0,path="/run/{name}-passt.sock" \\
  -netdev vhost-user,chardev=net0,id=net \\
  -device virtio-net-pci,netdev=net,mac=52:54:00:a9:f5:da,romfile=,addr=0x0,bus=pcie.{bus} \\
"""


    with open(f"{name}.sh", "w") as f:
        f.write(s)
