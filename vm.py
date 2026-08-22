#!/usr/bin/env python3

vms = {
    "hermes": {
        "cpu": 64,
        "ram": 128,
        "kernel": "/ssd/vm/vm-r17-nvda-pods-vsock-BOOTX64.efi",
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

for name, c in vms.items():
    s = ""
    s += "#!/usr/bin/env bash\n"
    s += "set -Eeuo pipefail\n\n"
    s += 'VM_NAME="' + name + '"\n\n'
    s += 'cleanup() { kill 0 2>/dev/null || true; ip netns del "ns-${VM_NAME}" 2>/dev/null || true; }\n'
    s += 'trap cleanup EXIT INT TERM\n\n'
    s += 'ip netns add "ns-${VM_NAME}"\n'
    s += 'ip link add "wg-${VM_NAME}" type wireguard\n'
    s += 'wg setconf "wg-${VM_NAME}" "/ssd/vm/ns-wg-${VM_NAME}.conf"\n'
    s += 'ip link set "wg-${VM_NAME}" netns "ns-${VM_NAME}"\n'
    s += 'ip -n "ns-${VM_NAME}" addr add 10.67.69.2/24 dev "wg-${VM_NAME}"\n'
    s += 'ip -n "ns-${VM_NAME}" link set "wg-${VM_NAME}" up\n'
    s += 'ip -n "ns-${VM_NAME}" route add default via 10.67.69.1 dev "wg-${VM_NAME}"\n\n'
    ps = "/run/${VM_NAME}-passt.sock"
    s += 'rm -f "' + ps + '"\n'
    s += 'ip netns exec "ns-${VM_NAME}" passt --foreground --vhost-user \\\n'
    s += '  --socket "' + ps + '" --repair-path none \\\n'
    s += '  --interface "wg-${VM_NAME}" --outbound-if4 "wg-${VM_NAME}" \\\n'
    s += '  --ipv4-only --mtu 1420 --address 10.67.69.2 --netmask 24 \\\n'
    s += '  --gateway 10.67.69.1 --no-map-gw --map-host-loopback none \\\n'
    s += '  --map-guest-addr none --tcp-ports all --udp-ports all &\n\n'
    s += 'for _ in {1..100}; do [[ -S "' + ps + '" ]] && break; sleep 0.01; done\n\n'
    fs_args = []
    for i, m in enumerate(c["mounts"]):
        fs = "/run/${VM_NAME}-fs-" + str(i) + ".sock"
        s += 'rm -f "' + fs + '"\n'
        ro = " --readonly" if m.get("readonly") else ""
        s += 'virtiofsd --socket-path="' + fs + '" --shared-dir=' + m["src"] + ro + ' &\n'
        s += 'for _ in {1..100}; do [[ -S "' + fs + '" ]] && break; sleep 0.01; done\n'
        fs_args.append("-chardev socket,id=fs" + str(i) + ",path=" + fs)
        fs_args.append("-device vhost-user-fs-pci,chardev=fs" + str(i) + ",tag=" + m["dst"])
    s += '\n'
    gpu_args = []
    if c["gpu"]:
        gpu_args = [
            "-object iommufd,id=iommufd0",
            "-device vfio-pci,host=0000:41:00.0,iommufd=iommufd0",
            "-device vfio-pci,host=0000:41:00.1,iommufd=iommufd0",
        ]
    vsock_arg = []
    if c["vsock"]:
        vsock_arg = ["-device vhost-vsock-pci,guest-cid=auto"]
    bus = c["net_bus"][2:]
    s += 'exec qemu-system-x86_64 \\\n'
    s += '  -nodefaults -no-user-config \\\n'
    s += '  -machine pc-q35-10.2,memory-backend=ram,usb=off,vmport=off,smm=off,dump-guest-core=off \\\n'
    s += '  -accel kvm \\\n'
    s += '  -cpu host,migratable=off \\\n'
    s += '  -object memory-backend-memfd,id=ram,size=' + str(c["ram"]) + 'G,share=on,hugetlb=on,hugetlbsize=1G \\\n'
    s += '  -smp ' + str(c["cpu"]) + ' \\\n'
    s += '  -rtc base=utc \\\n'
    s += '  -drive if=pflash,format=raw,readonly=on,file=/run/libvirt/nix-ovmf/edk2-x86_64-code.fd \\\n'
    s += '  -kernel ' + c["kernel"] + ' \\\n'
    s += '  -sandbox on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny \\\n'
    s += '  -object rng-random,id=rng,filename=/dev/urandom \\\n'
    s += '  -device virtio-rng-pci,rng=rng \\\n'
    s += '  -display none \\\n'
    for a in vsock_arg:
        s += '  ' + a + ' \\\n'
    s += '  -serial stdio -monitor none \\\n'
    s += '  -drive file=' + c["disk"] + ',if=virtio,format=qcow2,discard=unmap \\\n'
    for a in gpu_args:
        s += '  ' + a + ' \\\n'
    s += '  -chardev socket,id=net0,path="/run/${VM_NAME}-passt.sock" \\\n'
    s += '  -netdev vhost-user,chardev=net0,id=net \\\n'
    s += '  -device virtio-net-pci,netdev=net,mac=52:54:00:a9:f5:da,romfile=,addr=0x0,bus=pcie.' + bus + ' \\\n'
    for j, a in enumerate(fs_args):
        if j == len(fs_args) - 1:
            s += '  ' + a + '\n'
        else:
            s += '  ' + a + ' \\\n'
    out = "/home/hermes/.hermes/tigor-no-ai.worktrees/no-ai-main/" + name + ".sh"
    with open(out, "w") as f:
        f.write(s)
    print("wrote " + out)
